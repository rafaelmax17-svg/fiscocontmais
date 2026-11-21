'use strict';
// REINF × DCTFWeb (2.4.9) · Integra Contador (Serpro).
//
// • Conferência: para cada empresa com a EFD-Reinf FECHADA na competência, o sistema lê na Receita a DCTFWeb do período
//   (CONSDECCOMPLETA33 + CONSXMLDECLARACAO38) e compara, por código de receita, os débitos que vieram da REINF
//   (origens "REINF RET" e "REINF CP" da declaração) com o totalizador do fechamento (R-4099 / R-2099).
//   Resultado: Confere · Diverge (com a diferença) · Não apareceu · aguarda o fechamento da REINF.
// • Transmissão: a equipe (módulo EFD-Reinf) pede; só fica liberada com a DCTFWeb em andamento, a REINF fechada e todos
//   os códigos conferindo. O computador do Integra Contador (robô do Admin, com a chave e o e-CNPJ da Liddera) confere
//   de novo na hora, assina o XML da Receita com o e-CNPJ do escritório e transmite (TRANSDECLARACAO310); o recibo
//   (CONSRECIBO32) vai em PDF para a pasta do cliente (Relatórios › AAAA › MM). A equipe nunca vê a chave do Serpro.
// • Base legal: IN RFB 2.005/2021 (DCTFWeb; DCTF extinta para fatos geradores a partir de 01/2025); prazo de entrega no
//   último dia útil do mês seguinte ao dos fatos geradores (redação da IN RFB 2.248/2025).
//
// Firestore: dctfweb/<AAAA-MM>_<CNPJ> (equipe lê; só o robô/Admin grava) e dctfweb_pedidos/<id> (equipe cria; robô atende).
const fs = require('fs');
const path = require('path');
const os = require('os');
const auth = require('./auth');
const pastaCliente = require('./pasta_cliente');

const COL = 'dctfweb';
const COL_P = 'dctfweb_pedidos';
const MODULO = 'fiscal-reinf';
const LOTE = 8;
let D = null;
let _unsub = null, _robo = null, _rodando = false, _logTxt = [];
const _atendidos = new Set();

function init(deps) { D = deps; }
function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes(MODULO) : s.perfil === 'fiscal';
}
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
const _quem = () => { const s = auth.sessao() || {}; return s.nome || s.email || ''; };
const _so = (s) => String(s || '').replace(/\D/g, '');
const _r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;
const _comp = (c) => /^\d{4}-(0[1-9]|1[0-2])$/.test(c || '');
function _log(m) {
  _logTxt.push(`${new Date().toLocaleString('pt-BR')} ${m}`);
  try { fs.writeFileSync(path.join(D.userData(), 'dctfweb_log.txt'), _logTxt.slice(-600).join('\n')); } catch (_) {}
}
function _limpo(o) { return JSON.parse(JSON.stringify(o, (k, v) => (v === undefined ? null : v))); }

// débitos que a REINF mandou para a DCTFWeb, por código de receita (4 dígitos): totalizador do R-4099 e do R-2099
function esperadoDaReinf(doc) {
  const m = {};
  for (const f of [doc && doc.fech4099, doc && doc.fech2099]) {
    if (!f || !f.fechado) continue;
    (f.porCodigo || []).forEach((x) => { const c = _so(x.cod).slice(0, 4); if (c) m[c] = _r2((m[c] || 0) + (Number(x.enviado) || 0)); });
  }
  Object.keys(m).forEach((k) => { if (!m[k]) delete m[k]; });
  return m;
}
const _soma = (m) => _r2(Object.values(m || {}).reduce((a, v) => a + (Number(v) || 0), 0));
const _assinatura = (m) => Object.keys(m || {}).sort().map((k) => `${k}:${_r2(m[k]).toFixed(2)}`).join('|');
// 2.4.14: a conferência da REINF pelo serviço oficial traz só o recibo do fechamento (sem o totalizador). A "marca" da
// REINF passa a ser o recibo do R-4099/R-2099: se ele mudar depois da conferência, a transmissão é recusada.
const _api = (r) => !!(r && r.fonte === 'api');
const _marcaReinf = (r, esperado) => (_api(r) ? `recibos:${(r.fech4099 || {}).recibo || ''}|${(r.fech2099 || {}).recibo || ''}` : _assinatura(esperado));

// Confere · Diverge · Não apareceu (compara só os débitos de origem REINF na DCTFWeb)
function comparar(esperado, naDctf, situacao) {
  const e = esperado || {}, d = naDctf || {};
  const te = _soma(e), td = _soma(d);
  if (['semproc', 'erro'].includes(situacao)) return { comparacao: 'erro', diferenca: 0 };
  if (esperado === null && situacao === 'sem_declaracao') return { comparacao: 'sem_dctf', diferenca: 0 };      // REINF fechada (fonte 'api') e nenhuma DCTFWeb no período
  if (situacao === 'sem_declaracao' || (!Object.keys(d).length && te > 0)) return { comparacao: te > 0 ? 'nao_apareceu' : 'sem_debito', diferenca: _r2(-te) };
  if (esperado === null) return { comparacao: td > 0 ? 'recebida' : 'sem_debito', diferenca: 0, codigosDivergentes: [] };   // fonte 'api': sem totalizador
  const cods = new Set([...Object.keys(e), ...Object.keys(d)]);
  const difs = [...cods].map((c) => ({ cod: c, reinf: _r2(e[c] || 0), dctf: _r2(d[c] || 0) })).filter((x) => Math.abs(x.reinf - x.dctf) > 0.01);
  return { comparacao: difs.length ? 'diverge' : te > 0 ? 'confere' : 'sem_debito', diferenca: _r2(td - te), codigosDivergentes: difs };
}
// débitos que não vieram da REINF (eSocial / MIT): a transmissão pela equipe fica bloqueada (decisão de 18/11)
const outrasOrigens = (doc) => Object.entries((doc && doc.origens) || {}).filter(([k, v]) => !/^REINF/.test(k) && Number(v) > 0.009);
function podeTransmitir(doc) {
  return !!(doc && doc.situacao === 'em_andamento' && ['confere', 'recebida'].includes(doc.comparacao) && doc.reinfStatus === 'fechado' && _soma(doc.esperado) > 0 && !outrasOrigens(doc).length);
}

// ------------------------------------------------------------------ equipe: ver e pedir
async function _estadoRobo() {
  try {
    const { db, f } = _fs();
    const s = await f.getDoc(f.doc(db, 'fechamento_sn', 'integra'));
    const d = s.exists() ? s.data() : {};
    const hb = d.heartbeat && d.heartbeat.toMillis ? d.heartbeat.toMillis() : 0;
    return { ativo: !!d.ativo, online: !!hb && Date.now() - hb < 12 * 60 * 1000, nome: d.roboNome || '' };
  } catch (_) { return { ativo: false, online: false, nome: '' }; }
}
async function dados(comp) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo EFD-Reinf.');
  if (!_comp(comp)) throw new Error('Competência inválida.');
  const { db, f } = _fs();
  const docs = [], pedidos = [];
  (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).forEach((x) => docs.push(x.data()));
  try {
    (await f.getDocs(f.query(f.collection(db, COL_P), f.where('comp', '==', comp)))).forEach((x) => {
      const p = x.data();
      pedidos.push({ id: x.id, tipo: p.tipo, status: p.status, cnpjs: p.cnpjs || [], por: p.por || '', msg: p.msg || '', emMs: p.emMs || 0, fimMs: p.fimMs || 0 });
    });
  } catch (_) {}
  pedidos.sort((a, b) => b.emMs - a.emMs);
  return { comp, docs: docs.map((d) => ({ ...d, podeTransmitir: podeTransmitir(d) })), pedidos: pedidos.slice(0, 30), robo: await _estadoRobo() };
}

async function pedir({ tipo, comp, cnpjs, cnpj, auto } = {}) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo EFD-Reinf.');
  if (!['conferir', 'transmitir'].includes(tipo)) throw new Error('Pedido inválido.');
  if (!_comp(comp)) throw new Error('Competência inválida.');
  const robo = await _estadoRobo();
  if (!robo.ativo) throw new Error('O Integra Contador ainda não foi configurado pelo Admin.');
  const { db, f } = _fs();
  const s = auth.sessao() || {};
  let lista = (cnpj ? [cnpj] : Array.isArray(cnpjs) ? cnpjs : []).map(_so).filter((c) => c.length === 14);
  if (tipo === 'transmitir') {
    if (lista.length !== 1) throw new Error('Escolha uma empresa para transmitir.');
    const d = await f.getDoc(f.doc(db, COL, `${comp}_${lista[0]}`));
    if (d.exists() && outrasOrigens(d.data()).length) throw new Error('A DCTFWeb desta empresa também tem débitos de eSocial/MIT: a transmissão não é feita pelo sistema.');
    if (!d.exists() || !podeTransmitir(d.data())) throw new Error('A transmissão só é liberada com a DCTFWeb em andamento, a REINF fechada e todos os códigos conferindo.');
    // não deixa dois pedidos de transmissão da mesma empresa na fila
    const ab = await f.getDocs(f.query(f.collection(db, COL_P), f.where('comp', '==', comp)));
    let dup = false;
    ab.forEach((x) => { const p = x.data(); if (p.tipo === 'transmitir' && ['novo', 'rodando'].includes(p.status) && (p.cnpjs || []).includes(lista[0])) dup = true; });
    if (dup) throw new Error('A transmissão desta empresa já está na fila.');
  }
  const ref = await f.addDoc(f.collection(db, COL_P), {
    tipo, comp, cnpjs: lista, status: 'novo', auto: !!auto, por: _quem(), uid: s.uid || '', maquina: os.hostname(), emMs: Date.now(), em: f.serverTimestamp(),
  });
  return { id: ref.id, roboOnline: robo.online };
}

// depois da conferência da REINF (botão ou 12h): pede a conferência da DCTFWeb das empresas conferidas
async function pedirAuto(comp, cnpjs) {
  try {
    const robo = await _estadoRobo();
    if (!robo.ativo) return;
    await pedir({ tipo: 'conferir', comp, cnpjs: cnpjs || [], auto: true });
  } catch (_) {}
}

// ------------------------------------------------------------------ robô (computador do Integra Contador, Admin)
// chamado pelo integra.js quando este computador assume (ou deixa) o posto de robô
function ligarRobo(opc) {
  desligarRobo();
  _robo = opc;                             // { souRobo(), python(pedido), consumo({consulta, declaracao}) }
  let f, db;
  try { ({ db, f } = _fs()); } catch (_) { return; }
  _unsub = f.onSnapshot(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo')), (snap) => {
    if (!_robo || !_robo.souRobo()) return;
    const novos = [];
    snap.forEach((x) => { if (!_atendidos.has(x.id)) novos.push({ id: x.id, ...x.data() }); });
    novos.sort((a, b) => (a.emMs || 0) - (b.emMs || 0));
    if (novos.length) _fila(novos);
  }, () => {});
}
function desligarRobo() { if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; } _robo = null; }

async function _fila(novos) {
  if (_rodando) return;                   // o laço abaixo pega os que chegarem enquanto roda
  _rodando = true;
  try {
    let lista = novos;
    while (lista.length) {
      for (const p of lista) {
        if (_atendidos.has(p.id)) continue;
        _atendidos.add(p.id);
        await _atender(p).catch((e) => _log(`pedido ${p.id}: ${e.message || e}`));
      }
      // chegou mais alguma coisa enquanto atendia?
      const { db, f } = _fs();
      const mais = [];
      (await f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo')))).forEach((x) => { if (!_atendidos.has(x.id)) mais.push({ id: x.id, ...x.data() }); });
      lista = mais.sort((a, b) => (a.emMs || 0) - (b.emMs || 0));
    }
  } finally { _rodando = false; }
}

async function _atender(p) {
  const { db, f } = _fs();
  const ref = f.doc(db, COL_P, p.id);
  // reserva o pedido (outro robô pode ter pego)
  const ok = await f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    if (!s.exists() || s.data().status !== 'novo') return false;
    tx.update(ref, { status: 'rodando', roboNome: `${os.hostname()} · ${_quem()}`, inicioMs: Date.now() });
    return true;
  }).catch(() => false);
  if (!ok) return;
  _log(`===== pedido ${p.tipo} ${p.comp} (${(p.cnpjs || []).length || 'todas'} empresa(s)) · por ${p.por}`);
  let fim;
  try {
    fim = p.tipo === 'transmitir' ? await _transmitir(p) : await _conferir(p);
  } catch (e) {
    fim = { status: 'erro', msg: String(e.message || e).slice(0, 300) };
  }
  _log(`pedido ${p.id}: ${fim.status} · ${fim.msg || ''}`);
  await f.updateDoc(ref, _limpo({ ...fim, fimMs: Date.now() })).catch(() => {});
  try { D.notificar('dctf:mudou', { comp: p.comp }); } catch (_) {}
}

async function _reinfDocs(comp, cnpjs) {
  const { db, f } = _fs();
  const out = [];
  (await f.getDocs(f.query(f.collection(db, 'reinf'), f.where('comp', '==', comp)))).forEach((x) => { const d = x.data(); if (d && d.cnpj && (!cnpjs || !cnpjs.length || cnpjs.includes(d.cnpj))) out.push(d); });
  return out;
}

async function _conferir(p) {
  const { db, f } = _fs();
  const comp = p.comp;
  const reinfs = await _reinfDocs(comp, p.cnpjs);
  const atuais = new Map();
  (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).forEach((x) => atuais.set(x.data().cnpj, x.data()));
  const consultar = [];
  const cont = { confere: 0, diverge: 0, nao_apareceu: 0, aguarda: 0, erro: 0, mantidas: 0 };
  for (const r of reinfs) {
    const esperado = _api(r) ? null : esperadoDaReinf(r);
    const base = { comp, cnpj: r.cnpj, nome: r.nome || '', reinfStatus: r.status, fonte: _api(r) ? 'api' : 'ecac', esperado, totalReinf: _soma(esperado), reinfAssinatura: _marcaReinf(r, esperado) };
    if (r.status === 'aberto') {
      await f.setDoc(f.doc(db, COL, `${comp}_${r.cnpj}`), _limpo({ ...base, comparacao: 'aguarda', em: new Date().toISOString() }), { merge: true });
      cont.aguarda++; continue;
    }
    if (r.status !== 'fechado') continue;                     // sem movimento, nada enviado, sem procuração, erro: nada a comparar
    const ja = atuais.get(r.cnpj);
    // transmitida e a REINF não mudou: não gasta consulta
    if (ja && ja.situacao === 'transmitida' && ja.reinfAssinatura === base.reinfAssinatura && ['confere', 'recebida'].includes(ja.comparacao)) { cont.mantidas++; continue; }
    consultar.push(base);
  }
  const consumo = { consulta: 0, declaracao: 0 };
  for (let i = 0; i < consultar.length; i += LOTE) {
    const lote = consultar.slice(i, i + LOTE);
    const r = await _robo.python({ acao: 'dctf_conferir', comp, empresas: lote.map((x) => ({ cnpj: x.cnpj })) });
    if (!r.ok) throw new Error(r.erro || 'Falha na consulta da DCTFWeb.');
    consumo.consulta += (r.consumo || {}).consulta || 0;
    for (const x of r.resultados || []) {
      const b = lote.find((y) => y.cnpj === _so(x.cnpj)); if (!b) continue;
      const cmp = comparar(b.esperado, x.reinf, x.situacao);
      // fonte 'api': o que veio da REINF é o que está na DCTFWeb agora (fica guardado para conferir de novo na transmissão)
      if (b.esperado === null) { b.esperado = ['em_andamento', 'transmitida'].includes(x.situacao) ? (x.reinf || {}) : {}; b.totalReinf = _soma(b.esperado); }
      cont[cmp.comparacao] = (cont[cmp.comparacao] || 0) + 1;
      if (x.estrutura && x.estrutura.length) _log(`${b.nome}: blocos do XML → ${JSON.stringify(x.estrutura.slice(0, 2))}`);
      _log(`${b.nome}: DCTFWeb ${x.situacao} · REINF ${JSON.stringify(b.esperado)} × DCTFWeb ${JSON.stringify(x.reinf || {})} → ${cmp.comparacao}${x.msg ? ` (${x.msg})` : ''}`);
      await f.setDoc(f.doc(db, COL, `${comp}_${b.cnpj}`), _limpo({
        ...b, situacao: x.situacao, msg: x.msg || '', naDctf: x.reinf || {}, reinfOrigem: x.reinfOrigem || {}, totalDctf: _soma(x.reinf), origens: x.origens || {}, outros: x.outros || {},
        saldo: x.saldo ?? null, ...cmp, consultadoEm: new Date().toISOString(), consultadoPor: p.por || '',
      }), { merge: true });
    }
  }
  if (_robo.consumo) await _robo.consumo(consumo).catch(() => {});
  const partes = [`${cont.confere} confere(m)`, cont.recebida ? `${cont.recebida} recebida(s) na DCTFWeb` : '', cont.diverge ? `${cont.diverge} diverge(m)` : '', cont.nao_apareceu ? `${cont.nao_apareceu} não apareceu(ram)` : '', cont.aguarda ? `${cont.aguarda} aguardando o fechamento da REINF` : '', cont.erro ? `${cont.erro} com erro` : ''].filter(Boolean);
  return { status: 'feito', msg: partes.join(' · ') || 'nenhuma empresa com a REINF fechada', consultas: consumo.consulta };
}

async function _transmitir(p) {
  const { db, f } = _fs();
  const comp = p.comp, cnpj = (p.cnpjs || [])[0];
  const ref = f.doc(db, COL, `${comp}_${cnpj}`);
  const s = await f.getDoc(ref);
  const doc = s.exists() ? s.data() : null;
  if (!podeTransmitir(doc)) return { status: 'erro', msg: outrasOrigens(doc).length ? 'A DCTFWeb tem débitos de eSocial/MIT: a transmissão não é feita pelo sistema.' : 'A empresa não está liberada para transmitir (atualize a conferência).' };
  const [rf] = await _reinfDocs(comp, [cnpj]);
  const esperado = _api(rf) ? (doc.esperado || {}) : esperadoDaReinf(rf);
  if (!rf || rf.status !== 'fechado' || _marcaReinf(rf, esperado) !== doc.reinfAssinatura) return { status: 'erro', msg: 'A EFD-Reinf mudou depois da conferência: atualize a conferência antes de transmitir.' };
  const [a, m] = comp.split('-');
  const pasta = pastaCliente.pastaDoMes({ nome: doc.nome, cnpj }, a, m, true) || '';
  const r = await _robo.python({ acao: 'dctf_transmitir', comp, empresa: { cnpj, nome: doc.nome, esperado, pasta } });
  if (!r.ok) throw new Error(r.erro || 'Falha na transmissão.');
  const x = r.resultado || {};
  if (_robo.consumo) await _robo.consumo({ consulta: (r.consumo || {}).consulta || 0, declaracao: (r.consumo || {}).declaracao || 0 }).catch(() => {});
  if (!x.ok) {
    await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true });
    return { status: 'erro', msg: x.msg || 'A Receita não aceitou a transmissão.' };
  }
  await f.setDoc(ref, _limpo({
    situacao: 'transmitida', recibo: x.recibo || '', arquivo: x.arquivo || '', reciboAviso: x.aviso || '', ultimoErro: '',
    transmitidaEm: new Date().toISOString(), transmitidaPor: p.por || '', jaTransmitida: !!x.jaTransmitida,
  }), { merge: true });
  return { status: 'feito', msg: x.jaTransmitida ? 'A DCTFWeb já estava transmitida.' : `Transmitida${x.recibo ? ` · recibo ${x.recibo}` : ''}${x.aviso ? ` · ${x.aviso}` : ''}` };
}

module.exports = { init, podeUsar, dados, pedir, pedirAuto, ligarRobo, desligarRobo, esperadoDaReinf, comparar, podeTransmitir, outrasOrigens };
