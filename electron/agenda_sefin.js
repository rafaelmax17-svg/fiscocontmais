'use strict';
// Consulta automática da SEFIN-RO, em dias úteis, no primeiro FiscoCont+ aberto que tenha o e-CPF do contador
// instalado (de qualquer usuário com acesso aos módulos):
//   • Fisconforme: 07:45, 10:45, 13:45 e 16:45 (4x).
//   • DAREs em aberto (Débitos e DARE): 07:45, 09:45, 11:45, 13:45, 15:45 e 17:45 (6x).
//   • DAREs pagos (Conta Corrente, "00 - PAGO"): 08:15, 10:15, 12:30, 14:30, 16:15 e 18:00 (6x) — mês atual e, até o
//     10º dia útil do mês, também o mês anterior (fechamento no Domínio; pagamentos da virada do mês aparecem depois).
//
// • A vez de cada horário fica na nuvem (agenda_sefin/<AAAAMMDD>_<HHMM>): o primeiro computador que pega o horário
//   consulta; os outros não repetem e só recebem o resultado (números, cartões do menu e o aviso de novidade).
// • Só consulta com o certificado do CONTADOR: o CPF do e-CPF instalado tem de ser o mesmo da última leitura do
//   Fisconforme (ou o escolhido pelo Admin neste computador). Com outro e-CPF, este computador não participa.
// • Nunca atrapalha quem está usando: se houver consulta da SEFIN em andamento (leitura, DARE, extrato), espera.
// • Se quem pegou o horário não terminar em 40 minutos (60 nos pagos) — computador desligado ou sistema atualizado no
//   meio —, outro pode assumir até o próximo horário do mesmo grupo.

const os = require('os');
const auth = require('./auth');
const fisc = require('./fisconforme');
const dare = require('./dare');
const giam = require('./giam');

// horários (dias úteis, hora do computador)
const HORARIOS = ['07:45', '10:45', '13:45', '16:45'];                       // Fisconforme
const HORARIOS_D = ['07:45', '09:45', '11:45', '13:45', '15:45', '17:45'];    // DAREs em aberto (Débitos e DARE)
const HORARIOS_PG = ['08:15', '10:15', '12:30', '14:30', '16:15', '18:00'];   // DAREs pagos (Conta Corrente)
const HORARIOS_G = ['08:00'];                                                 // recibos GIAM/SPED (1x ao dia, competência anterior)
// Cada horário vale até o próximo do mesmo grupo (no máximo 2 h): se o computador que pegou a vez for fechado no meio
// da consulta (ou atualizar o sistema), outro computador assume depois do prazo, ainda dentro da janela.
// Achado real (16/11/2026): a janela era de 55 min e o prazo de 40 — a consulta das 07:45 ficou "rodando" e ninguém
// mais podia assumir, porque a janela já tinha fechado quando o prazo venceu.
const JANELA_MAX_MIN = 120;
const PRAZO_MIN = 40;               // quem pegou o horário e não terminou nesse tempo perde a vez
const PRAZO_PG_MIN = 60;            // pagos de 2 meses demoram mais
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
const _min = (h) => { const [hh, mm] = h.split(':').map(Number); return hh * 60 + mm; };

// Grade do dia: Fisconforme e DAREs em aberto no mesmo horário rodam juntos (um slot); os pagos têm slots próprios.
function _grade() {
  const fd = {};
  HORARIOS.forEach((h) => { (fd[h] = fd[h] || { f: false, d: false }).f = true; });
  HORARIOS_D.forEach((h) => { (fd[h] = fd[h] || { f: false, d: false }).d = true; });
  const lista = (horas, extra) => horas.slice().sort((a, b) => _min(a) - _min(b)).map((h, i, arr) => {
    const prox = arr[i + 1] ? _min(arr[i + 1]) : Infinity;
    return { h, fim: Math.min(prox, _min(h) + JANELA_MAX_MIN), ...extra(h) };
  });
  return [
    ...lista(Object.keys(fd), (h) => ({ tipo: 'debitos', f: fd[h].f, d: fd[h].d })),
    ...lista(HORARIOS_PG, () => ({ tipo: 'pagos', f: false, d: false })),
    // a GIAM tem a janela até as 18h: se ninguém estava com o e-CPF às 8h, o primeiro computador do dia faz
    ...HORARIOS_G.map((h) => ({ h, fim: _min('18:00'), tipo: 'giam', f: false, d: false })),
  ];
}

// slots com a janela aberta agora (pode haver um de débitos e um de pagos ao mesmo tempo)
function slotsAtuais(agora = new Date()) {
  const dia = agora.getDay();
  if (dia === 0 || dia === 6) return [];                         // só dias úteis
  const m = agora.getHours() * 60 + agora.getMinutes();
  const data = `${agora.getFullYear()}${_2(agora.getMonth() + 1)}${_2(agora.getDate())}`;
  return _grade().filter((g) => m >= _min(g.h) && m < g.fim).sort((a, b) => _min(a.h) - _min(b.h))
    .map((g) => ({ ...g, id: `${data}_${g.h.replace(':', '')}${g.tipo === 'pagos' ? '_pg' : g.tipo === 'giam' ? '_giam' : ''}` }));
}
const slotAtual = (agora) => slotsAtuais(agora)[0] || null;

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
        if (x.status === 'rodando' && idadeMin < (['pagos', 'giam'].includes(slot.tipo) ? PRAZO_PG_MIN : PRAZO_MIN)) return false;
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
  const slots = slotsAtuais();
  if (!slots.length) return;
  for (const slot of slots) {
    const podeG = slot.tipo === 'giam' && giam.podeUsar(s);
    const podeD = slot.tipo !== 'giam' && (slot.tipo === 'pagos' || slot.d) && dare.podeUsar(s);
    const podeF = slot.f && fisc.podeUsar(s);
    if (!podeF && !podeD && !podeG) continue;
    if (fisc.portal.ocupado()) return;                            // alguém está usando a SEFIN agora: espera
    if (!(await _temCertificado())) return;
    if (!(await _pegarVez(slot))) continue;                       // outro computador já fez (ou está fazendo)
    await _executa(slot, podeF, podeD);
    return;                                                       // um slot por vez; o próximo vai no minuto seguinte
  }
}

async function _executa(slot, podeF, podeD) {
  _rodando = true;
  const res = { status: 'ok' };
  const espera = async () => { for (let i = 0; i < 30 && fisc.portal.ocupado(); i++) await new Promise((r) => setTimeout(r, 2000)); };
  try {
    if (podeF) {
      try { const r = await fisc.ler({ auto: true }); res.fisconforme = { novas: r.novas || 0 }; }
      catch (e) { res.fisconforme = { erro: String(e.message || e).slice(0, 200) }; }
    }
    if (slot.tipo === 'giam') {
      await espera();
      const comp = giam.compAnterior();
      try { const r = await giam.ler(comp, { auto: true }); res.giam = { comp, processado: r.processado || 0, nao: r.nao_processado || 0, erros: r.erro || 0 }; }
      catch (e) { res.giam = { erro: String(e.message || e).slice(0, 200) }; }
    } else if (podeD && slot.tipo === 'pagos') {
      res.pagos = {};
      for (const mes of mesesPagos()) {
        await espera();
        try { const r = await dare.lerPagos(mes, { auto: true }); res.pagos[mes] = { qtd: r.qtd || 0, falhas: r.falhas || 0 }; }
        catch (e) { res.pagos[mes] = { erro: String(e.message || e).slice(0, 200) }; }
      }
    } else if (podeD) {
      await espera();                                             // espera a janela da consulta ser liberada pela leitura anterior
      try { const r = await dare.ler(String(new Date().getFullYear()), { auto: true }); res.dare = { novos: r.novos || 0 }; }
      catch (e) { res.dare = { erro: String(e.message || e).slice(0, 200) }; }
    }
    // erro só quando TUDO o que rodou deu erro (assim outro computador tenta de novo); antes, uma consulta só de
    // DAREs com erro ficava marcada como "ok" e não era repetida
    const feitos = [res.fisconforme, res.dare, res.giam, ...Object.values(res.pagos || {})].filter(Boolean);
    if (!feitos.length || feitos.every((x) => x.erro)) res.status = 'erro';
  } finally {
    await _marca(slot, res);
    _rodando = false;
    try { D.notificar('sefin:auto', { fim: true, ...res }); } catch (_) {}
  }
}

function estado() {
  return { horarios: HORARIOS, horariosDare: HORARIOS_D, horariosPagos: HORARIOS_PG, horariosGiam: HORARIOS_G, rodando: _rodando, proximo: _proximo(), proximoGiam: _proximoGiam() };
}
function _proximoGiam(agora = new Date()) {
  for (let k = 0; k < 8; k++) {
    const d = new Date(agora); d.setDate(d.getDate() + k);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    const [hh, mm] = HORARIOS_G[0].split(':').map(Number); const x = new Date(d); x.setHours(hh, mm, 0, 0);
    if (x > agora) return x.toISOString();
  }
  return '';
}
function _proximo(agora = new Date()) {
  for (let k = 0; k < 8; k++) {
    const d = new Date(agora); d.setDate(d.getDate() + k);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    for (const g of _grade().sort((a, b) => _min(a.h) - _min(b.h))) {
      const [hh, mm] = g.h.split(':').map(Number);
      const x = new Date(d); x.setHours(hh, mm, 0, 0);
      if (x > agora) return x.toISOString();
    }
  }
  return '';
}

module.exports = { init, tick, estado, slotAtual, slotsAtuais, mesesPagos, HORARIOS, HORARIOS_D, HORARIOS_PG };
