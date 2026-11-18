'use strict';
// Conferência automática da EFD-Reinf: 1x por dia útil às 12:00 (até as 18:00, se nenhum computador estava aberto ao
// meio-dia), no primeiro FiscoCont+ aberto que tenha o certificado do escritório instalado e acesso ao módulo.
// • A vez do dia fica na nuvem (agenda_reinf/<AAAAMMDD>): só um computador confere; os outros veem o resultado.
// • Competência conferida: o mês anterior (a REINF de outubro é enviada em novembro).
// • Se quem pegou a vez não terminar em 3 horas (computador desligado no meio), outro assume dentro da janela.

const os = require('os');
const auth = require('./auth');
const reinf = require('./reinf');

const HORA = '12:00', FIM = '18:00';
const PRAZO_MIN = 180;
const COL = 'agenda_reinf';
let D = null, _timer = null, _rodando = false, _cert = { em: 0, ok: false };
const _2 = (n) => String(n).padStart(2, '0');
const _min = (h) => { const [a, b] = h.split(':').map(Number); return a * 60 + b; };

function init(deps) {
  D = deps;
  if (_timer) clearInterval(_timer);
  _timer = setInterval(() => { tick().catch(() => {}); }, 60 * 1000);
}
function compAnterior(d = new Date()) { const x = new Date(d.getFullYear(), d.getMonth() - 1, 1); return `${x.getFullYear()}-${_2(x.getMonth() + 1)}`; }
function _janela(agora = new Date()) {
  if (agora.getDay() === 0 || agora.getDay() === 6) return null;
  const m = agora.getHours() * 60 + agora.getMinutes();
  if (m < _min(HORA) || m >= _min(FIM)) return null;
  return `${agora.getFullYear()}${_2(agora.getMonth() + 1)}${_2(agora.getDate())}`;
}
async function _temCert() {
  if (Date.now() - _cert.em < 30 * 60000) return _cert.ok;
  _cert = { em: Date.now(), ok: await reinf.certificadoInstalado().catch(() => false) };
  return _cert.ok;
}
async function _pegarVez(id) {
  const db = auth.db(); const f = auth.fsMod();
  if (!db || !f || !f.runTransaction) return false;
  const ref = f.doc(db, COL, id);
  const s = auth.sessao() || {};
  const eu = { status: 'rodando', por: s.nome || s.email || '', maquina: os.hostname(), em: new Date().toISOString() };
  try {
    return await f.runTransaction(db, async (t) => {
      const d = await t.get(ref);
      if (d.exists()) {
        const x = d.data();
        if (x.status === 'ok') return false;
        const idade = (Date.now() - Date.parse(x.em || 0)) / 60000;
        if (x.status === 'rodando' && idade < PRAZO_MIN) return false;
        if (x.status === 'erro' && idade < 30) return false;
        if ((x.tentativas || 0) >= 3) return false;
        t.set(ref, { ...eu, tentativas: (x.tentativas || 0) + 1 });
        return true;
      }
      t.set(ref, { ...eu, tentativas: 1 });
      return true;
    });
  } catch (_) { return false; }
}
async function tick() {
  if (_rodando || !D) return;
  const s = auth.sessao();
  if (!s || !reinf.podeUsar(s) || reinf.ocupado()) return;
  const id = _janela();
  if (!id) return;
  if (D.ocupado && D.ocupado()) return;                 // outra consulta usando a internet agora: espera o próximo minuto
  if (!(await _temCert())) return;
  if (!(await _pegarVez(id))) return;
  _rodando = true;
  let res = { status: 'ok' };
  try {
    const r = await reinf.conferir({ comp: compAnterior(), auto: true });
    res = { status: r.ok ? 'ok' : 'erro', comp: r.comp, empresas: r.total, ok: r.ok, erros: r.erros };
  } catch (e) { res = { status: 'erro', erro: String(e.message || e).slice(0, 300) }; }
  finally {
    try { const db = auth.db(); const f = auth.fsMod(); await f.setDoc(f.doc(db, COL, id), { ...res, fimEm: new Date().toISOString() }, { merge: true }); } catch (_) {}
    _rodando = false;
    try { D.notificar('reinf:auto', { fim: true, ...res }); } catch (_) {}
  }
}
function proxima(agora = new Date()) {
  for (let k = 0; k < 8; k++) {
    const d = new Date(agora); d.setDate(d.getDate() + k);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    const x = new Date(d); x.setHours(12, 0, 0, 0);
    if (x > agora) return x.toISOString();
  }
  return '';
}
module.exports = { init, tick, proxima, compAnterior, HORA };
