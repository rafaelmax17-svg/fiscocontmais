'use strict';
// Consulta automática da SEFIN-RO, em dias úteis, no primeiro FiscoCont+ aberto que tenha o e-CPF do contador
// instalado (de qualquer usuário com acesso aos módulos):
//   • Fisconforme e débitos em aberto (Débitos e DARE): 07:45, 10:45, 13:45 e 16:45.
//   • DAREs pagos (Conta Corrente, "00 - PAGO"): 12:30 e 18:00 — mês atual e, até o 10º dia útil do mês, também o
//     mês anterior (fechamento no Domínio; pagamentos da virada do mês aparecem depois).
//
// • A vez de cada horário fica na nuvem (agenda_sefin/<AAAAMMDD>_<HHMM>): o primeiro computador que pega o horário
//   consulta; os outros não repetem e só recebem o resultado (números, cartões do menu e o aviso de novidade).
// • Só consulta com o certificado do CONTADOR: o CPF do e-CPF instalado tem de ser o mesmo da última leitura do
//   Fisconforme (ou o escolhido pelo Admin neste computador). Com outro e-CPF, este computador não participa.
// • Nunca atrapalha quem está usando: se houver consulta da SEFIN em andamento (leitura, DARE, extrato), espera.
// • Se quem pegou o horário não terminar em 40 minutos (computador desligado no meio), outro pode assumir.

const os = require('os');
const auth = require('./auth');
const fisc = require('./fisconforme');
const dare = require('./dare');

const HORARIOS = ['07:45', '10:45', '13:45', '16:45'];
const HORARIOS_PG = ['12:30', '18:00'];
const JANELA_MIN = 55;              // depois do horário, até quando ainda tenta
const PRAZO_MIN = 40;               // quem pegou o horário e não terminou nesse tempo perde a vez
const COL = 'agenda_sefin';

let D = null;
let _timer = null;
let _rodando = false;
let _cert = { em: 0, ok: false, cpf: '' };

function init(deps) {
  D = deps;
  if (_timer) clearInterval(_timer);
  _timer = setInterval(() => { tick().catch(() => {}); }, 60 * 1000);
  setTimeout(() => { tick().catch(() => {}); }, 30 * 1000);
}

const _2 = (n) => String(n).padStart(2, '0');
function slotAtual(agora = new Date()) {
  const dia = agora.getDay();
  if (dia === 0 || dia === 6) return null;                       // só dias úteis
  const todos = [...HORARIOS.map((h) => [h, 'debitos']), ...HORARIOS_PG.map((h) => [h, 'pagos'])];
  for (const [h, tipo] of todos) {
    const [hh, mm] = h.split(':').map(Number);
    const ini = new Date(agora); ini.setHours(hh, mm, 0, 0);
    const fim = new Date(ini.getTime() + JANELA_MIN * 60000);
    if (agora >= ini && agora < fim) {
      return { id: `${agora.getFullYear()}${_2(agora.getMonth() + 1)}${_2(agora.getDate())}_${h.replace(':', '')}${tipo === 'pagos' ? '_pg' : ''}`, h, tipo };
    }
  }
  return null;
}

// meses dos pagos: o atual e, até o 10º dia útil, também o anterior
function mesesPagos(agora = new Date()) {
  const m = (d) => `${d.getFullYear()}${_2(d.getMonth() + 1)}`;
  let uteis = 0;
  for (let d = 1; d <= agora.getDate(); d++) { const x = new Date(agora.getFullYear(), agora.getMonth(), d).getDay(); if (x !== 0 && x !== 6) uteis++; }
  const out = [m(agora)];
  if (uteis <= 10) out.unshift(m(new Date(agora.getFullYear(), agora.getMonth() - 1, 1)));
  return out;
}

// e-CPF do contador neste computador? (a lista de certificados do Windows é lida no máximo a cada 30 min)
async function _temCertificado() {
  if (Date.now() - _cert.em < 30 * 60000) return _cert.ok;
  _cert = { em: Date.now(), ok: false, cpf: '' };
  try {
    const est = await fisc.estado();
    const esc = est && est.escolhido;
    if (!esc || !esc.cpf) return false;
    const { db, f } = { db: auth.db(), f: auth.fsMod() };
    const meta = db ? (await f.getDoc(f.doc(db, 'fisconforme', '_meta'))).data() : null;
    const cpfContador = meta && meta.contador && meta.contador.cpf ? String(meta.contador.cpf) : '';
    const sessao = auth.sessao() || {};
    // com leitura anterior: tem de ser o mesmo CPF; sem leitura ainda: só o computador do Admin participa
    _cert.ok = cpfContador ? cpfContador === String(esc.cpf) : sessao.perfil === 'admin';
    _cert.cpf = esc.cpf;
  } catch (_) { _cert.ok = false; }
  return _cert.ok;
}

// pega a vez do horário na nuvem (transação: só um computador consegue)
async function _pegarVez(slot) {
  const db = auth.db(); const f = auth.fsMod();
  if (!db || !f || !f.runTransaction) return false;
  const ref = f.doc(db, COL, slot.id);
  const s = auth.sessao() || {};
  const eu = { status: 'rodando', por: s.nome || s.email || '', maquina: os.hostname(), em: new Date().toISOString() };
  try {
    return await f.runTransaction(db, async (t) => {
      const d = await t.get(ref);
      if (d.exists()) {
        const x = d.data();
        if (x.status === 'ok') return false;
        const idadeMin = (Date.now() - Date.parse(x.em || 0)) / 60000;
        if (x.status === 'rodando' && idadeMin < (slot.tipo === 'pagos' ? 90 : PRAZO_MIN)) return false;   // pagos de 2 meses demoram mais
        if (x.status === 'erro' && idadeMin < 10) return false;        // espera um pouco antes de tentar de novo
        if ((x.tentativas || 0) >= 3) return false;
        t.set(ref, { ...eu, tentativas: (x.tentativas || 0) + 1 });
        return true;
      }
      t.set(ref, { ...eu, tentativas: 1 });
      return true;
    });
  } catch (_) { return false; }
}

async function _marca(slot, dados) {
  try {
    const db = auth.db(); const f = auth.fsMod();
    await f.setDoc(f.doc(db, COL, slot.id), { ...dados, fimEm: new Date().toISOString() }, { merge: true });
  } catch (_) {}
}

async function tick() {
  if (_rodando || !D) return;
  const s = auth.sessao();
  if (!s) return;
  const slot = slotAtual();
  if (!slot) return;
  const podeD = dare.podeUsar(s), podeF = slot.tipo === 'pagos' ? false : fisc.podeUsar(s);
  if (!podeF && !podeD) return;
  if (fisc.portal.ocupado()) return;                              // alguém está usando a SEFIN agora: espera
  if (!(await _temCertificado())) return;
  if (!(await _pegarVez(slot))) return;
  _rodando = true;
  const res = { status: 'ok' };
  try {
    if (podeF) {
      try { const r = await fisc.ler({ auto: true }); res.fisconforme = { novas: r.novas || 0 }; }
      catch (e) { res.fisconforme = { erro: String(e.message || e).slice(0, 200) }; }
    }
    if (podeD && slot.tipo === 'pagos') {
      res.pagos = {};
      for (const mes of mesesPagos()) {
        for (let i = 0; i < 30 && fisc.portal.ocupado(); i++) await new Promise((r) => setTimeout(r, 2000));
        try { const r = await dare.lerPagos(mes, { auto: true }); res.pagos[mes] = { qtd: r.qtd || 0, falhas: r.falhas || 0 }; }
        catch (e) { res.pagos[mes] = { erro: String(e.message || e).slice(0, 200) }; }
      }
      if (Object.values(res.pagos).every((x) => x.erro)) res.status = 'erro';
    } else if (podeD) {
      // espera a janela da consulta ser liberada pela leitura anterior
      for (let i = 0; i < 30 && fisc.portal.ocupado(); i++) await new Promise((r) => setTimeout(r, 2000));
      try { const r = await dare.ler(String(new Date().getFullYear()), { auto: true }); res.dare = { novos: r.novos || 0 }; }
      catch (e) { res.dare = { erro: String(e.message || e).slice(0, 200) }; }
    }
    if ((res.fisconforme && res.fisconforme.erro) && (!res.dare || res.dare.erro)) res.status = 'erro';
  } finally {
    await _marca(slot, res);
    _rodando = false;
    try { D.notificar('sefin:auto', { fim: true, ...res }); } catch (_) {}
  }
}

function estado() {
  return { horarios: HORARIOS, horariosPagos: HORARIOS_PG, rodando: _rodando, proximo: _proximo() };
}
function _proximo(agora = new Date()) {
  for (let k = 0; k < 8; k++) {
    const d = new Date(agora); d.setDate(d.getDate() + k);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    for (const h of HORARIOS) {
      const [hh, mm] = h.split(':').map(Number);
      const x = new Date(d); x.setHours(hh, mm, 0, 0);
      if (x > agora) return x.toISOString();
    }
  }
  return '';
}

module.exports = { init, estado, slotAtual, mesesPagos, HORARIOS, HORARIOS_PG };
