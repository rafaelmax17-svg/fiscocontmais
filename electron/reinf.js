'use strict';
// Conferência da EFD-Reinf — 2.4.14: serviço oficial de consulta da EFD-Reinf (pedido do Rafael, 21/11/2026).
//
// Até a 2.4.13 o sistema abria o eCAC, trocava o perfil de procurador empresa por empresa e lia as telas da EFD-Reinf.
// A Receita passou a recusar a troca de perfil feita pelo sistema ("a execução possui atributos que caracteriza acesso
// automatizado") e, quando a empresa tem mensagem importante não lida na Caixa Postal, o eCAC trava até ela ser aberta —
// e abrir dá ciência da intimação (Decreto 70.235/1972, art. 23, § 2º, III, "b"). O sistema não contorna nenhuma das
// duas coisas: a conferência agora usa só o serviço que a Receita publica para programas.
//
//   • Consulta de recibos da EFD-Reinf (Manual de Orientação ao Desenvolvedor v2.8, cap. 6.1):
//       GET https://reinf.receita.economia.gov.br/consulta/reciboevento/R4099/1/<CNPJ raiz>/<AAAA-MM>
//       GET https://reinf.receita.economia.gov.br/consulta/reciboevento/R2099/1/<CNPJ raiz>/<AAAA-MM>
//     com o e-CNPJ do escritório como certificado de cliente (procurador com procuração eletrônica que inclua a
//     EFD-Reinf, feita para o CNPJ matriz). Devolve o recibo, a data/hora de recepção e a situação do fechamento.
//     Sem tela, sem captcha, sem trocar perfil e sem tocar na Caixa Postal.
//   • Valores por imposto: a DCTFWeb do período (Integra Contador, electron/dctfweb.js) — o fechamento da REINF manda
//     os débitos para lá; o computador do Integra confere logo depois desta conferência.
//   • Resultado na nuvem (reinf/<AAAA-MM>_<CNPJ>, fonte 'api'), visto por toda a equipe.
// Roda sozinho 1x por dia (agenda_reinf.js) ou no botão. Passo a passo em reinf_log.txt e as respostas da Receita
// (endereço, código HTTP e o começo do XML) em reinf_rede.txt, na pasta de dados.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, BrowserWindow, session } = require('electron');
const auth = require('./auth');
const nfePortal = require('./nfe_portal');
const ecac = require('./reinf_ecac');

const MODULO = 'fiscal-reinf';
const COL = 'reinf';
const HOST = 'https://reinf.receita.economia.gov.br';
const API = `${HOST}/consulta/reciboevento`;
const PARTICAO = 'persist:reinf-api';
// e-CNPJ do escritório (procurador). Pode ser trocado pelo Admin em reinf.json (pasta de dados) → { "cnpjCertificado": "..." }
const CNPJ_ESCRITORIO = '36714399000110';
const PAUSA = 800;            // entre uma consulta e outra: o manual avisa que consultas em sequência excessiva são uso abusivo

let D = null;                 // { userData(), notificar(c, d), empresasLocais(), janelaPai() }
let _win = null, _rodando = false, _parar = false, _certFaltou = false, _pronta = false;
let _logTxt = [], _rede = [];
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');
const _fmtCnpj = (c) => _so(c).replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
const _limpo = (o) => JSON.parse(JSON.stringify(o === undefined ? null : o));
const _vivo = () => _win && !_win.isDestroyed();
const _r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;

function _cfg() { try { return JSON.parse(fs.readFileSync(path.join(D.userData(), 'reinf.json'), 'utf-8')); } catch (_) { return {}; } }
const cnpjCertificado = () => _so(_cfg().cnpjCertificado) || CNPJ_ESCRITORIO;

function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes(MODULO) : s.perfil === 'fiscal';
}
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }

function _log(m) {
  _logTxt.push(`${new Date().toLocaleTimeString('pt-BR')} ${m}`);
  try { fs.writeFileSync(path.join(D.userData(), 'reinf_log.txt'), _logTxt.slice(-800).join('\n')); } catch (_) {}
}
function _logRede(m) {
  _rede.push(`${new Date().toLocaleTimeString('pt-BR')} ${m}`);
  try { fs.writeFileSync(path.join(D.userData(), 'reinf_rede.txt'), _rede.slice(-400).join('\n')); } catch (_) {}
}
function _prog(txt, extra) { try { D.notificar('reinf:progresso', { txt, ...(extra || {}) }); } catch (_) {} }

function init(deps) {
  D = deps;
  ecac.init({ userData: () => D.userData(), janelaPai: () => (D.janelaPai ? D.janelaPai() : null), runFiscal: (a, o) => D.runFiscal(a, o),
    log: (m) => _log(m), prog: (t, x) => _prog(t, x), cnpjCertificado: () => cnpjCertificado(), parando: () => _parar });
  app.on('select-client-certificate', (event, webContents, url, lista, callback) => {
    if (!_vivo() || webContents.id !== _win.webContents.id) return;
    const alvo = lista.find((c) => _cnpjCert(c) === cnpjCertificado());
    _log(`a Receita pediu o certificado (${String(url).split('?')[0].slice(0, 60)}): ${lista.length} no Windows · ${alvo ? 'usando o e-CNPJ do escritório' : 'e-CNPJ do escritório NÃO instalado'}`);
    event.preventDefault();
    if (!alvo) _certFaltou = true;
    callback(alvo || null);
  });
}
function _cnpjCert(c) {
  const cn = String((c.subject && c.subject.commonName) || c.subjectName || '');
  const m = cn.match(/:(\d{14})\b/) || String(c.subjectName || '').match(/(?<!\d)(\d{14})(?!\d)/);
  return m ? m[1] : '';
}
async function certificadoInstalado() {
  if (process.platform !== 'win32') return false;
  return (await nfePortal.cnpjsInstalados()).includes(cnpjCertificado());
}

// ------------------------------------------------------------------ consulta (janela oculta: só para o certificado)
// A janela nunca aparece. Ela existe porque é por ela que o Windows entrega o e-CNPJ do escritório à conexão; a primeira
// consulta abre o endereço da própria Receita e as seguintes são feitas a partir dele (mesmo endereço, mesma conexão).
function _janela() {
  if (_vivo()) return _win;
  _pronta = false;
  _win = new BrowserWindow({ show: false, width: 900, height: 600, title: 'FiscoCont+ · EFD-Reinf',
    webPreferences: { partition: PARTICAO, contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false, javascript: true } });
  _win.on('closed', () => { _win = null; _pronta = false; });
  return _win;
}

// lê a resposta (XML; se vier JSON, também serve): registros com recibo e ocorrências (código/descrição)
const JS_GET = (url) => `(async () => {
  try {
    const r = await fetch(${JSON.stringify(url)}, { credentials: 'include', cache: 'no-store', headers: { Accept: 'application/xml, text/xml, application/json, */*' } });
    const t = await r.text();
    const regs = [], ocorr = [];
    const add = (o) => { const ks = Object.keys(o); if (ks.some((k) => /recibo/i.test(k) && !/arqbase/i.test(k))) regs.push(o);
      const kd = ks.find((k) => /^(dsc|desc|mensagem|msg)/i.test(k)); if (kd) ocorr.push({ cod: o[ks.find((k) => /^(cod|cd)/i.test(k))] || '', txt: String(o[kd] || '').slice(0, 400) }); };
    if (/^\\s*[\\[{]/.test(t)) {
      const walk = (v) => { if (Array.isArray(v)) { v.forEach(walk); return; } if (v && typeof v === 'object') { const o = {}; let folha = false;
        Object.entries(v).forEach(([k, x]) => { if (x == null || typeof x !== 'object') { o[k] = String(x ?? ''); folha = true; } else walk(x); }); if (folha) add(o); } };
      try { walk(JSON.parse(t)); } catch (_) {}
    } else {
      const doc = new DOMParser().parseFromString(t, 'application/xml');
      if (!doc.getElementsByTagName('parsererror').length) {
        const pais = new Set();
        [...doc.getElementsByTagName('*')].forEach((el) => { if (!el.children.length && el.parentElement) pais.add(el.parentElement); });
        pais.forEach((p) => { const o = {}; [...p.children].forEach((c) => { if (!c.children.length) o[c.localName] = (c.textContent || '').trim(); }); add(o); });
      }
    }
    return { http: r.status, ct: r.headers.get('content-type') || '', texto: t.slice(0, 1500), regs, ocorr };
  } catch (e) { return { http: 0, erro: String((e && e.message) || e) }; }
})()`;

async function _get(url) {
  const w = _janela();
  if (!_pronta) {
    // primeira consulta: abre o endereço na própria janela (o Windows entrega o certificado nessa hora)
    let http = 0, falha = '';
    const nav = (_e, _u, code) => { http = code || http; };
    const erro = (_e, cod, desc) => { if (cod !== -3) falha = `${desc} (${cod})`; };
    w.webContents.on('did-navigate', nav);
    w.webContents.on('did-fail-load', erro);
    await w.loadURL(url).catch((e) => { if (!falha) falha = String(e.message || e); });
    w.webContents.removeListener('did-navigate', nav);
    w.webContents.removeListener('did-fail-load', erro);
    if (_certFaltou) throw new Error('o certificado do escritório não está instalado no Windows deste computador.');
    if (!http) {
      _logRede(`GET ${url.replace(HOST, '')} → falhou: ${falha}`);
      if (/CLIENT_AUTH|CERT|SSL|-1(0[0-9]|1[0-9])\b/i.test(falha)) throw new Error(`a Receita não aceitou o certificado do escritório (${falha}).`);
      throw new Error(`não consegui falar com o serviço da EFD-Reinf (${falha || 'sem resposta'}).`);
    }
    _pronta = true;
  }
  let r = await w.webContents.executeJavaScript(JS_GET(url), true).catch((e) => ({ http: 0, erro: String(e.message || e) }));
  if (r.http === 429) {            // "aguarde alguns minutos": espera 1 minuto e tenta uma vez só
    _log('a Receita pediu para aguardar (HTTP 429): esperando 1 minuto…');
    _prog('A Receita pediu uma pausa: aguardando 1 minuto…');
    for (let i = 0; i < 60 && !_parar; i++) await _sleep(1000);
    r = await w.webContents.executeJavaScript(JS_GET(url), true).catch((e) => ({ http: 0, erro: String(e.message || e) }));
  }
  _logRede(`GET ${url.replace(HOST, '')} → HTTP ${r.http || 0}${r.erro ? ` · ${r.erro}` : ''} · ${(r.regs || []).length} registro(s) · ${String(r.texto || '').replace(/\s+/g, ' ').slice(0, 600)}`);
  return r;
}

// ------------------------------------------------------------------ leitura do fechamento
const _campo = (o, re) => { const k = Object.keys(o || {}).find((x) => re.test(x)); return k ? String(o[k] || '').trim() : ''; };
// AAAAMMDDHHMMSS (ou ISO) → DD/MM/AAAA HH:MM
function _dh(s) {
  const t = String(s || '');
  let m = t.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})/);
  if (!m) m = t.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : t;
}
const _ord = (s) => _so(s).padEnd(14, '0');

// situação do evento (manual v2.8): 1 Ativo · 2 Retificado · 3 Excluído · 4 Em processamento (R-2099) · 5 Recusado
function _fechamento(r, ev) {
  const textos = (r.ocorr || []).map((x) => `${x.cod ? `${x.cod} ` : ''}${x.txt}`).filter(Boolean);
  const msg = textos.join(' · ').slice(0, 300) || (r.erro || '');
  if (/PROCURA/i.test(`${msg} ${r.texto || ''}`) || r.http === 403) return { semProcuracao: true, msg };
  if (r.http === 495 || r.http === 496) return { erro: `a Receita não aceitou o certificado do escritório (HTTP ${r.http}).` };
  if (r.http === 404) return { fechado: false, nada: true };
  if (r.http !== 200) return { erro: `o serviço da EFD-Reinf respondeu HTTP ${r.http || 0}${msg ? `: ${msg}` : ''}` };
  const regs = (r.regs || []).map((o) => ({ recibo: _campo(o, /recibo/i), sit: _campo(o, /situa/i), dh: _campo(o, /^dh|datahora|recep/i), protocolo: _campo(o, /protocolo/i), id: _campo(o, /^id/i) }))
    .filter((x) => x.recibo || x.protocolo).sort((a, b) => _ord(a.dh).localeCompare(_ord(b.dh)));
  if (!regs.length) return { fechado: false, nada: true };
  const ult = regs[regs.length - 1];
  const base = { recepcao: _dh(ult.dh), protocolo: ult.protocolo || '', nRegistros: regs.length };
  if (ult.sit === '4') return { fechado: false, processando: true, ...base, recibo: ult.recibo || '' };
  if (ult.sit === '5') return { fechado: false, recusado: true, ...base, recibo: ult.recibo || '' };
  const ativos = regs.filter((x) => !x.sit || x.sit === '1');
  if (!ativos.length) return { fechado: false, nada: true };
  const a = ativos[ativos.length - 1];
  // o recibo não diz se o R-${ev} é fechamento ou reabertura: fechamentos e reaberturas se alternam, então um número par de
  // eventos ativos quer dizer que o último foi uma reabertura (período aberto de novo)
  if (ativos.length > 1 && ativos.length % 2 === 0) return { fechado: false, reaberto: true, recibo: a.recibo, recepcao: _dh(a.dh), nRegistros: regs.length };
  return { fechado: true, recibo: a.recibo, recepcao: _dh(a.dh), dhProcess: _dh(a.dh), id: a.id || '', nRegistros: regs.length };
}

async function _empresa(emp, comp) {
  const raiz = _so(emp.cnpj).slice(0, 8);
  const fech = {};
  for (const ev of ['4099', '2099']) {
    if (_parar) break;
    _prog(`${emp.nome}: fechamento R-${ev}…`);
    const r = await _get(`${API}/R${ev}/1/${raiz}/${comp}`);
    fech[ev] = _fechamento(r, ev);
    const f = fech[ev];
    _log(`${emp.nome} R-${ev}: HTTP ${r.http || 0} · ${f.semProcuracao ? 'sem procuração' : f.erro ? f.erro : f.fechado ? `fechado · recibo ${f.recibo} · ${f.recepcao}` : f.reaberto ? 'reaberto' : f.recusado ? 'recusado' : f.processando ? 'em processamento' : 'sem fechamento'}${f.nRegistros > 1 ? ` (${f.nRegistros} registros)` : ''}`);
    if (f.semProcuracao) {
      return { status: 'sem_procuracao', fonte: 'api', msg: f.msg ? `a Receita respondeu: ${f.msg}` : 'A Liddera não tem procuração eletrônica desta empresa com poderes da EFD-Reinf (ou ela venceu).' };
    }
    if (f.erro) return { status: 'erro', fonte: 'api', msg: f.erro };
    await _sleep(PAUSA);
  }
  const f4 = fech['4099'] || {}, f2 = fech['2099'] || {};
  const avisos = [];
  [[f4, '4099'], [f2, '2099']].forEach(([f, ev]) => {
    if (f.reaberto) avisos.push(`R-${ev}: o período foi reaberto e ainda não foi fechado de novo.`);
    if (f.recusado) avisos.push(`R-${ev}: o fechamento enviado foi recusado pela Receita.`);
    if (f.processando) avisos.push(`R-${ev}: o fechamento ainda está em processamento na Receita.`);
  });
  const pendente = [f4, f2].some((f) => f.reaberto || f.recusado || f.processando);
  const status = pendente ? 'aberto' : (f4.fechado || f2.fechado) ? 'fechado' : 'sem_fechamento';
  return { status, fonte: 'api', fech4099: f4, fech2099: f2, eventos: [], totais: {}, avisos, msg: avisos.join(' ') };
}

// ------------------------------------------------------------------ valores da REINF (eCAC, com a pessoa)
const _sigRecibos = (d) => `${(d.fech4099 || {}).recibo || ''}|${(d.fech2099 || {}).recibo || ''}`;
// junta ao resultado da consulta oficial o que foi lido no eCAC (eventos, totalizador por código, PDF/XML): recibo,
// data e situação continuam os da consulta oficial
function _aplicaEcac(doc, src) {
  const tt = !!(src.temTotalizador ?? (src.ecac && src.ecac.temTotalizador));
  const f = (a, b) => ({ ...(b || {}), ...(a || {}), porCodigo: (b || {}).porCodigo || [], porNatureza: (b || {}).porNatureza || [], pdf: (b || {}).pdf || '', xml: (b || {}).xml || '', semMovimento: !!(b || {}).semMovimento });
  return { ...doc, fonte: tt ? 'ecac' : 'api', eventos: src.eventos || [], totais: tt ? src.totais : (doc.totais || {}), somaEventos: src.somaEventos || {},
    pasta: src.pasta || doc.pasta || '', fech4099: f(doc.fech4099, src.fech4099), fech2099: f(doc.fech2099, src.fech2099),
    ecac: { ok: true, recibos: _sigRecibos(doc), em: (src.ecac && src.ecac.em) || new Date().toISOString(), temTotalizador: tt },
    avisos: [...(doc.avisos || []), ...((src.ecac ? [] : src.avisos) || [])] };
}

// ------------------------------------------------------------------ empresas e nuvem
async function _grava(comp, emp, dados) {
  const { db, f } = _fs();
  const s = auth.sessao() || {};
  await f.setDoc(f.doc(db, COL, `${comp}_${emp.cnpj}`), _limpo({ cnpj: emp.cnpj, nome: emp.nome, comp, ...dados, em: new Date().toISOString(), por: s.nome || s.email || '' }));
}

// empresas conferidas: lista guardada na nuvem (reinf/_empresas), começando pelas conhecidas do sistema (uma por CNPJ raiz)
async function empresas() {
  const { db, f } = _fs();
  const ref = f.doc(db, COL, '_empresas');
  const d = await f.getDoc(ref).catch(() => null);
  const salvo = d && d.exists() ? d.data() : null;
  const mapa = new Map();
  const add = (cnpj, nome, extra) => {
    const c = _so(cnpj); if (c.length !== 14 || !nome) return;
    const raiz = c.slice(0, 8);                                  // a REINF é por CNPJ raiz: uma linha por empresa (matriz)
    const ja = mapa.get(raiz);
    if (!ja || (c.slice(8, 12) === '0001' && ja.cnpj.slice(8, 12) !== '0001')) mapa.set(raiz, { cnpj: c, nome: String(nome).trim(), ativa: true, ...(ja ? { ativa: ja.ativa } : {}), ...(extra || {}) });
  };
  (salvo && salvo.lista || []).forEach((x) => add(x.cnpj, x.nome, { ativa: x.ativa !== false }));
  if (!salvo) {
    try { (D.empresasLocais ? D.empresasLocais() : []).forEach((x) => add(x.cnpj, x.nome)); } catch (_) {}
    try { (await f.getDocs(f.collection(db, 'dare'))).forEach((x) => { const v = x.data(); if (v && v.cnpj) add(v.cnpj, v.razao || v.nome); }); } catch (_) {}
    try { const c = await f.getDoc(f.doc(db, 'fechamento_sn', 'cadastro')); Object.values((c.exists() && c.data().empresas) || {}).forEach((x) => add(x.cnpj, x.nome)); } catch (_) {}
    try { (await f.getDocs(f.collection(db, 'certificados'))).forEach((x) => add(x.id, (x.data() || {}).nome)); } catch (_) {}
    const lista = [...mapa.values()].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    try { await f.setDoc(ref, { lista, em: new Date().toISOString() }); } catch (_) {}
    return lista;
  }
  return [...mapa.values()].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
}
async function salvarEmpresas(lista) {
  const { db, f } = _fs();
  const limpa = (lista || []).map((x) => ({ cnpj: _so(x.cnpj), nome: String(x.nome || '').trim(), ativa: x.ativa !== false })).filter((x) => x.cnpj.length === 14 && x.nome);
  await f.setDoc(f.doc(db, COL, '_empresas'), { lista: limpa, em: new Date().toISOString() });
  return { lista: limpa };
}

// dados de uma competência: os documentos da REINF + os valores por imposto da DCTFWeb (Integra Contador)
// Série R-4000 (origem "REINF RET" na DCTFWeb): CSRF por código; o resto é IRRF.
// Série R-2000 (origem "REINF CP"): Funrural do R-2055 (aquisição de produção rural): 1656 contribuição previdenciária,
// 1646 GILRAT e 1213 Senar; os demais (1162/1141 retenção do R-2010, CPRB, clube etc.) ficam em INSS.
const _IMP = { 6228: 'csll', 5987: 'csll', 6230: 'pis', 5979: 'pis', 6243: 'cofins', 5960: 'cofins', 5952: 'agreg' };
const _FUNRURAL = new Set(['1656', '1646', '1213']);
const _CP = new Set(['1162', '1141', '1151', '2985', '2991']);
function _imposto(cod, origem) {
  const c = String(cod).slice(0, 4);
  if (_FUNRURAL.has(c)) return 'funrural';
  if (origem === 'REINF CP' || _CP.has(c)) return 'inss';
  return _IMP[c] || 'irrf';
}
function _comDctf(doc, dc) {
  if (!doc || doc.fonte !== 'api' || !dc || !dc.naDctf || !['em_andamento', 'transmitida'].includes(dc.situacao)) return doc;
  const totais = { irrf: 0, csll: 0, cofins: 0, pis: 0, agreg: 0, inss: 0, funrural: 0 };
  const org = dc.reinfOrigem || {};
  const codigos = Object.entries(dc.naDctf).map(([cod, v]) => ({ cod, enviado: _r2(v), imposto: _imposto(cod, org[cod]) }));
  codigos.forEach((x) => { totais[x.imposto] = _r2(totais[x.imposto] + x.enviado); });
  return { ...doc, totais, dctfCodigos: codigos, totaisDe: 'dctfweb', dctfEm: dc.consultadoEm || '' };
}
async function dados(comp) {
  const { db, f } = _fs();
  const [ca, cm] = comp.split('-').map(Number);
  const ant = cm === 1 ? `${ca - 1}-12` : `${ca}-${String(cm - 1).padStart(2, '0')}`;
  const ler = async (col, c) => {
    const out = [];
    const q = f.query(f.collection(db, col), f.where('comp', '==', c));
    (await f.getDocs(q)).forEach((x) => out.push(x.data()));
    return out;
  };
  const [atual, anterior, emps, meta, dctf] = await Promise.all([ler(COL, comp), ler(COL, ant).catch(() => []), empresas(),
    f.getDoc(f.doc(db, COL, `_meta_${comp}`)).catch(() => null), ler('dctfweb', comp).catch(() => [])]);
  const porCnpj = new Map(dctf.map((x) => [x.cnpj, x]));
  // os valores mostrados são SEMPRE os da REINF (eCAC); a DCTFWeb fica na aba REINF × DCTFWeb, para comparar
  void porCnpj;
  return { comp, anterior: ant, empresas: emps, docs: atual,
    docsAnterior: anterior.map((x) => ({ cnpj: x.cnpj, status: x.status, nEventos: (x.eventos || []).length, fechado: x.status === 'fechado' })),
    meta: meta && meta.exists() ? meta.data() : null, rodando: _rodando, certificado: cnpjCertificado() };
}

// ------------------------------------------------------------------ conferência
// conferir: todas as empresas ativas (ou só os CNPJs pedidos) na competência
async function conferir({ comp, cnpjs, auto } = {}) {
  if (_rodando) throw new Error('A conferência da EFD-Reinf já está em andamento.');
  if (!podeUsar()) throw new Error('Sem acesso ao módulo EFD-Reinf.');
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(comp || '')) throw new Error('Competência inválida.');
  if (process.platform === 'win32' && !(await certificadoInstalado())) throw new Error(`O certificado do escritório (e-CNPJ ${_fmtCnpj(cnpjCertificado())}) não está instalado no Windows deste computador.`);
  const lista = (await empresas()).filter((x) => x.ativa !== false && (!cnpjs || !cnpjs.length || cnpjs.includes(x.cnpj)));
  if (!lista.length) throw new Error('Nenhuma empresa para conferir.');
  _rodando = true; _parar = false; _certFaltou = false; _logTxt = []; _rede = [];
  const s = auth.sessao() || {};
  const res = { comp, total: lista.length, ok: 0, erros: 0 };
  _log(`conferência ${comp} · ${lista.length} empresa(s) · serviço oficial de consulta da EFD-Reinf · certificado ${_fmtCnpj(cnpjCertificado())}`);
  try {
    const { db, f } = _fs();
    await f.setDoc(f.doc(db, COL, `_meta_${comp}`), { rodando: true, inicio: new Date().toISOString(), por: s.nome || s.email || '', maquina: os.hostname(), auto: !!auto, fonte: 'api' }, { merge: true }).catch(() => {});
    const anteriores = new Map();
    (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp))).catch(() => ({ forEach() {} }))).forEach((x) => { const d = x.data(); if (d && d.cnpj) anteriores.set(d.cnpj, d); });
    const precisaEcac = [];
    let errosSeguidos = 0;
    for (const [n, emp] of lista.entries()) {
      if (_parar) break;
      _prog(`${emp.nome} (${n + 1} de ${lista.length})…`, { feitas: n, total: lista.length });
      _log(`===== ${emp.nome} (${_fmtCnpj(emp.cnpj)}) · ${comp}`);
      let r;
      try { r = await _empresa(emp, comp); } catch (e) { r = { status: 'erro', fonte: 'api', msg: String(e.message || e).slice(0, 300) }; }
      if (_certFaltou) throw new Error('o certificado do escritório não está instalado no Windows deste computador.');
      if (_parar && r.status !== 'erro' && !r.fech4099) break;
      // valores já lidos no eCAC para os MESMOS recibos: continuam valendo; recibo novo → precisa ler no eCAC
      const ant = anteriores.get(emp.cnpj);
      if (r.status === 'fechado') {
        if (ant && ant.ecac && ant.ecac.ok && ant.ecac.recibos === _sigRecibos(r)) r = _aplicaEcac(r, ant);
        else precisaEcac.push(emp);
      }
      if (r.status === 'erro') res.erros++; else res.ok++;
      await _grava(comp, emp, r).catch((e) => _log(`gravar na nuvem: ${e.message || e}`));
      try { D.notificar('reinf:empresa', { comp, cnpj: emp.cnpj }); } catch (_) {}
      // o mesmo erro de conexão/certificado em sequência: para em vez de repetir dezenas de vezes
      errosSeguidos = r.status === 'erro' ? errosSeguidos + 1 : 0;
      if (errosSeguidos >= 5) { _log('5 erros seguidos: conferência interrompida.'); throw new Error(`a conferência parou depois de 5 erros seguidos: ${r.msg || 'erro'}`); }
    }
    // valores da REINF: só as empresas com fechamento novo, no eCAC, com a pessoa clicando em "Alterar" (nunca na
    // conferência automática das 12h, que roda sem ninguém olhando)
    res.ecacPendentes = precisaEcac.length;
    if (precisaEcac.length && !_parar && !auto && process.platform === 'win32') {
      _log(`valores pelo eCAC: ${precisaEcac.length} empresa(s) com fechamento novo`);
      const atuais = new Map();
      (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).forEach((x) => { const d = x.data(); if (d && d.cnpj) atuais.set(d.cnpj, d); });
      const e2 = await ecac.ler(precisaEcac, comp, anteriores, async (emp, r) => {
        const doc = atuais.get(emp.cnpj); if (!doc) return;
        let novo;
        if (r.ok) novo = _aplicaEcac(doc, r);
        else {
          const av = r.caixaPostal ? 'Mensagem importante na Caixa Postal do eCAC: os valores não foram lidos. Abra a mensagem pelo eCAC quando decidir dar ciência.'
            : r.semProcuracao ? `eCAC: sem procuração para trocar o perfil${r.msg ? ` (${String(r.msg).toLowerCase()})` : ''}.`
              : r.pulada ? 'Valores da REINF: empresa pulada no eCAC.' : `Valores da REINF: ${r.erro || 'não lidos no eCAC'}.`;
          novo = { ...doc, caixaPostal: !!r.caixaPostal, avisos: [...(doc.avisos || []), av], msg: av };
        }
        if (r.ok) novo.caixaPostal = false;
        await _grava(comp, emp, novo).catch((e) => _log(`gravar na nuvem: ${e.message || e}`));
        try { D.notificar('reinf:empresa', { comp, cnpj: emp.cnpj }); } catch (_) {}
      });
      res.ecacLidas = e2.lidas; res.ecacPuladas = e2.puladas;
      if (e2.parouPor) _log(`leitura pelo eCAC parou: ${e2.parouPor}`);
    }
    await f.setDoc(f.doc(db, COL, `_meta_${comp}`), { rodando: false, fim: new Date().toISOString(), por: s.nome || s.email || '', maquina: os.hostname(), auto: !!auto, ok: res.ok, erros: res.erros, total: lista.length, fonte: 'api', ecacPendentes: res.ecacPendentes || 0, ecacLidas: res.ecacLidas || 0 }, { merge: true }).catch(() => {});
    // REINF × DCTFWeb: o computador do Integra Contador lê a DCTFWeb das empresas conferidas (valores por imposto)
    if (!_parar) { try { await require('./dctfweb').pedirAuto(comp, cnpjs && cnpjs.length ? lista.map((x) => x.cnpj) : []); } catch (_) {} }
  } catch (e) {
    try { const { db, f } = _fs(); await f.setDoc(f.doc(db, COL, `_meta_${comp}`), { rodando: false, fim: new Date().toISOString(), erro: String(e.message || e).slice(0, 300) }, { merge: true }); } catch (_) {}
    throw e;
  } finally {
    _rodando = false;
    try { if (_vivo()) _win.destroy(); } catch (_) {}
    _win = null; _pronta = false;
    try { await session.fromPartition(PARTICAO).clearCache(); } catch (_) {}
    _prog('', { fim: true });
  }
  return res;
}
function parar() { _parar = true; return { ok: true }; }
const ocupado = () => _rodando;

module.exports = { init, podeUsar, conferir, parar, dados, empresas, salvarEmpresas, certificadoInstalado, ocupado, cnpjCertificado, MODULO, _fechamento, _comDctf, _aplicaEcac };
