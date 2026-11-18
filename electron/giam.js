'use strict';
// Recibos GIAM/SPED Fiscal · SEFIN-RO (Portal do Contribuinte) — 2.4.9, pedido do Rafael (18/11/2026).
//
// Tarefa da equipe que vira automática: pegar o recibo de processamento da GIAM/SPED Fiscal de cada empresa.
//   1. entra no Portal do Contribuinte com o e-CPF do contador (a mesma entrada do Fisconforme e dos Débitos e DARE);
//   2. GIAM › "2ª via recibo": pega TODAS as inscrições da lista "Inscrição Estadual" (as empresas ligadas ao contador);
//   3. para cada uma: Período Inicial e Final = competência (AAAAMM) › Consultar:
//        • com linha na tabela (Referência · Retificadora · Data Entrega): "Imprimir Recibo" › PDF na pasta do cliente,
//          Relatórios\AAAA\MM da COMPETÊNCIA, "Recibo GIAM SPED MMAAAA - IE <IE>.pdf" (sem a pasta da empresa: Notas
//          Automáticas, com aviso);
//        • sem linha: confere de novo numa página nova (mês e últimos 12 meses) e só então decide:
//            - Simples Nacional na competência (pasta "Fiscal - Simples Nacional" ou cadastro da Receita) → fora da conferência;
//            - CNPJ baixado/inapto/suspenso antes da competência (cadastro da Receita) → fora da conferência;
//            - nenhuma GIAM/SPED nos últimos 12 meses → "Sem entregas" (inscrição provavelmente baixada), fora da conferência;
//            - entregava e não entregou esta competência → "Não processado" (alarme).
//   4. resultado na nuvem (giam/<AAAA-MM>_<IE>), visto pela equipe na tela "Recibos GIAM/SPED".
// Roda sozinho 1x por dia útil às 08:00 (agenda_sefin, num só computador com o e-CPF do contador) ou no botão.
// O passo a passo fica no fisconforme_log.txt (mesma janela do portal) e a última tela em giam_ultima.png.

const fs = require('fs');
const path = require('path');
const auth = require('./auth');
const fisc = require('./fisconforme');
const pastaCliente = require('./pasta_cliente');

const P = fisc.portal;
const MODULO = 'fiscal-giam';
const COL = 'giam';
const URL_GIAM = 'https://portalcontribuinte.sefin.ro.gov.br/GIAM/';
const HOST_PORTAL = /(^|\.)portalcontribuinte\.sefin\.ro\.gov\.br$/i;
const SSO = 'https://sitafesec-sso-int.sefin.ro.gov.br/acesso_externo/acesso_digital?request_url=';
const SSO_PORTAL = [`${SSO}${encodeURIComponent('http://portalcontribuinte.sefin.ro.gov.br/SsoLogin')}&login_template=default`,
  `${SSO}${encodeURIComponent(URL_GIAM)}&login_template=default`];
const PASTA_AUTO = 'G:\\Drives compartilhados\\Fiscal - Lucro Real\\00 - Arquivos FISCAL\\Notas Automáticas - FiscoCont';
const SEM_IMPRESSAO = 'try { window.print = function () {}; } catch (e) {}';

let D = null, _lendo = false, _abriu = null;
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');
const _mesmaIE = (a, b) => _so(a).replace(/^0+/, '') === _so(b).replace(/^0+/, '');
const _limpaNome = (s) => String(s || '').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '');
function _prog(txt, extra) { try { D.notificar('giam:progresso', { txt, ...(extra || {}) }); } catch (_) {} }

function init(deps) { D = deps; }
function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes(MODULO) : s.perfil === 'fiscal';
}
function _exige() { if (!podeUsar()) throw new Error('Sem acesso ao módulo Recibos GIAM/SPED.'); }
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
function compAnterior(d = new Date()) { const x = new Date(d.getFullYear(), d.getMonth() - 1, 1); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`; }

// ------------------------------------------------------------------ janela (a mesma do portal)
async function _janela() {
  const w = P.janela();
  if (!w.__giam) {
    w.__giam = true;
    w.webContents.setWindowOpenHandler(({ url }) => { _abriu = url; P.log(`GIAM · nova janela pedida: ${String(url).split('?')[0]}`); return { action: 'deny' }; });
    try {
      const dbg = w.webContents.debugger;
      if (!dbg.isAttached()) dbg.attach('1.3');
      await dbg.sendCommand('Page.enable');
      await dbg.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: SEM_IMPRESSAO, runImmediately: true });
    } catch (e) { P.log(`GIAM · aviso: impressão automática não desligada (${e.message || e})`); }
    w.webContents.on('dom-ready', () => { try { w.webContents.mainFrame.framesInSubtree.forEach((fr) => fr.executeJavaScript(SEM_IMPRESSAO).catch(() => {})); } catch (_) {} });
  }
  return w;
}
async function _jsF(code, limite = 15000) {
  const w = P.win(); if (!w || w.isDestroyed()) return null;
  let frames = [];
  try { frames = w.webContents.mainFrame.framesInSubtree; } catch (_) { frames = [w.webContents.mainFrame]; }
  for (const fr of frames) {
    try {
      const r = await Promise.race([fr.executeJavaScript(code, true), new Promise((_r, rej) => setTimeout(() => rej(new Error('tempo')), limite))]);
      if (r) return { r, fr };
    } catch (_) {}
  }
  return null;
}
const _noFrame = (fr, code) => Promise.race([fr.executeJavaScript(code, true), new Promise((_r, rej) => setTimeout(() => rej(new Error('a página não respondeu')), 20000))]);
async function _espera(code, ms, passo = 700) { const ate = Date.now() + ms; while (Date.now() < ate) { const x = await _jsF(code); if (x) return x; await _sleep(passo); } return null; }
async function _print() { try { fs.writeFileSync(path.join(D.userData(), 'giam_ultima.png'), (await P.win().webContents.capturePage()).toPNG()); } catch (_) {} }

// ------------------------------------------------------------------ scripts das páginas
const JS_BASE = `const limpa = (s) => String(s == null ? '' : s).replace(/\\s+/g, ' ').trim();
  const vis = (e) => !!(e && e.getClientRects && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const selIE = () => [...document.querySelectorAll('select')].find((s) => [...s.options].some((o) => /^\\s*\\d{8,14}\\s*-\\s*\\S/.test(o.textContent)));`;
// tela de envio ("Envio de arquivos de GIAM/SPED") ou o formulário da 2ª via (inscrição + período)
const JS_ESTADO = `(() => { ${JS_BASE}
  const t = document.body ? document.body.innerText : '';
  const s = selIE();
  const form = s && /PER[IÍ]ODO\\s+INICIAL/i.test(t);
  const bt2via = [...document.querySelectorAll('a, button, input[type=button], input[type=submit]')].filter(vis).find((b) => /2\\s*[ªaº°]?\\.?\\s*via\\s+recibo/i.test(b.innerText || b.value || ''));
  if (form) return { form: true, ies: [...s.options].map((o) => ({ v: o.value, t: limpa(o.textContent) })).filter((o) => /^\\d{8,14}\\s*-/.test(o.t)) };
  if (bt2via || /ENVIO DE ARQUIVOS DE GIAM/i.test(t)) return { envio: true, bt2via: !!bt2via };
  return null; })()`;
const JS_CLICA_2VIA = `(() => { ${JS_BASE}
  const b = [...document.querySelectorAll('a, button, input[type=button], input[type=submit]')].filter(vis).find((x) => /2\\s*[ªaº°]?\\.?\\s*via\\s+recibo/i.test(x.innerText || x.value || ''));
  if (!b) return false; b.click(); return true; })()`;
// escolhe a inscrição, preenche Período Inicial e Final (AAAAMM) e clica em Consultar (as tabelas antigas ficam marcadas)
const jsConsultar = (v, perIni, perFim) => `(() => { ${JS_BASE}
  const s = selIE(); if (!s) return { erro: 'a lista de inscrições não apareceu' };
  const setv = (el, val) => { const d = Object.getOwnPropertyDescriptor(el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value'); d.set.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  setv(s, ${JSON.stringify(v)});
  const ins = [...document.querySelectorAll('input')].filter(vis).filter((i) => !i.type || /^(text|number|tel|search)$/i.test(i.type));
  const perto = (i, re) => { for (let e = i, k = 0; e && k < 4; e = e.parentElement, k++) { if (re.test(limpa(e.innerText || ''))) return true; } return false; };
  const lbl = (i, re) => { const id = i.id && document.querySelector('label[for="' + i.id + '"]'); return (id && re.test(id.innerText)) || re.test((i.name || '') + ' ' + (i.id || '') + ' ' + (i.placeholder || '')); };
  let ini = ins.find((i) => lbl(i, /inicial|inicio|ini\\b/i)) || ins.find((i) => perto(i, /Per[ií]odo Inicial/i) && !perto(i, /Per[ií]odo Final/i));
  let fim = ins.find((i) => lbl(i, /final|fim\\b/i)) || ins.find((i) => i !== ini && perto(i, /Per[ií]odo Final/i));
  if (!ini || !fim) { const seis = ins.filter((i) => /^\\d{6}$/.test(i.value) || /yyyymm|aaaamm/i.test(i.placeholder || '')); ini = ini || seis[0]; fim = fim || seis[1]; }
  if (!ini || !fim) return { erro: 'os campos de período não apareceram' };
  setv(ini, ${JSON.stringify(perIni)}); setv(fim, ${JSON.stringify(perFim || perIni)});
  document.querySelectorAll('table').forEach((t) => { t.dataset.fcVelho = '1'; });
  window.__fcConsultou = Date.now();          // esta página é a de ANTES do Consultar: o resultado tem que vir da página nova
  const b = [...document.querySelectorAll('input[type=submit], input[type=button], button, a')].filter(vis).find((x) => /^\\s*consultar\\s*$/i.test(x.value || x.innerText || ''));
  if (!b) return { erro: 'o botão Consultar não apareceu' };
  b.click(); return { ok: true }; })()`;
// resultado: tabela nova (Referência · Retificadora · Data Entrega) ou mensagem de "nenhum"
// Achado real (18/11): depois de uma inscrição "sem recibo", a próxima era lida ainda na página antiga (com a mensagem de
// "nenhum" da anterior) e ficava "Não processado" mesmo processada na SEFIN. Agora a página de antes do Consultar não vale.
const JS_RES = `(() => { ${JS_BASE}
  if (window.__fcConsultou && Date.now() - window.__fcConsultou < 15000) return null;
  const t = [...document.querySelectorAll('table')].filter((x) => !x.dataset.fcVelho && vis(x)).find((x) => /REFER[EÊ]NCIA/i.test(x.innerText) && /ENTREGA/i.test(x.innerText));
  if (t) {
    const linhas = [...t.rows].slice(1).map((r, i) => { const c = [...r.cells].map((x) => limpa(x.innerText));
      return { i, ref: c[0] || '', retif: c[1] || '', entrega: c[2] || '', bt: !![...r.querySelectorAll('a, button, input')].find((b) => /imprimir/i.test(b.innerText || b.value || '')) }; }).filter((l) => /\\d{6}|\\d{2}\\/\\d{4}/.test(l.ref));
    return { tabela: true, linhas, ie: (selIE() || {}).value || '' };
  }
  const txt = document.body ? document.body.innerText : '';
  if (/nenhum|n[ãa]o\\s+(foram\\s+)?encontrad|n[ãa]o\\s+h[áa]\\s+recibo|sem\\s+recibo/i.test(txt)) return { tabela: false, certo: true, msg: limpa((txt.match(/[^\\n]*(nenhum|n[ãa]o\\s+(foram\\s+)?encontrad|n[ãa]o\\s+h[áa]|sem\\s+recibo)[^\\n]*/i) || [''])[0]).slice(0, 200) };
  return null; })()`;
const jsImprimir = (i) => `(() => { ${JS_BASE}
  const t = [...document.querySelectorAll('table')].filter((x) => !x.dataset.fcVelho && vis(x)).find((x) => /REFER[EÊ]NCIA/i.test(x.innerText) && /ENTREGA/i.test(x.innerText));
  if (!t) return { erro: 'a tabela de recibos sumiu' };
  const r = [...t.rows].slice(1)[${i}]; if (!r) return { erro: 'a linha do recibo não apareceu' };
  const b = [...r.querySelectorAll('a, button, input')].find((x) => /imprimir/i.test(x.innerText || x.value || ''));
  if (!b) return { erro: 'o botão Imprimir Recibo não apareceu' };
  b.click(); return { ok: true, href: b.href || '' }; })()`;

const JS_EMPS_FISC = `(() => [...document.querySelectorAll('#busca_contribuinte option')].map((o) => ({ cnpj: (o.value || '').replace(/\\D/g, ''), t: (o.textContent || '').replace(/\\s+/g, ' ').trim() })).filter((x) => x.cnpj.length === 14))()`;
let _empsPortal = [];

// ------------------------------------------------------------------ entrada
async function _entrar() {
  P.canal('giam:progresso');
  _prog('Entrando no portal da SEFIN com o certificado do contador…');
  await P.loginSso();
  // logo depois da entrada a janela está no Fisconforme, que lista as empresas do contador com IE e CNPJ
  try {
    const l = await P.js(JS_EMPS_FISC);
    if (Array.isArray(l) && l.length) { _empsPortal = l; P.log(`GIAM · ${l.length} empresa(s) do contador com CNPJ (lista do portal)`); }
  } catch (_) {}
  await _janela();
  _prog('Abrindo a GIAM no Portal do Contribuinte…');
  await P.vai(URL_GIAM, 45000);
  const ate = Date.now() + 100000;
  let ssoTent = 0, cliques = 0, voltas = 0, ult = '';
  while (Date.now() < ate) {
    const e = await _jsF(JS_ESTADO);
    if (e && e.r.form) { P.log(`GIAM · 2ª via do recibo aberta: ${e.r.ies.length} inscrição(ões) na lista`); return e.r.ies; }
    if (e && e.r.envio) {
      if (e.r.bt2via) { await _jsF(JS_CLICA_2VIA); P.log('GIAM · clicou em "2ª via recibo"'); await _sleep(2500); continue; }
    }
    const u = new URL(P.win().webContents.getURL() || 'about:blank');
    if (P.ehSso(u.host)) {
      const st = await P.js(P.JS_ESTADO_LOGIN).catch(() => null);
      if (st && st.texto !== ult) { P.log(`SSO (GIAM): ${st.texto}`); ult = st.texto; }
      if (st && st.captcha) throw new Error('O portal pediu captcha na entrada e a consulta parou. Entre uma vez pelo navegador e tente de novo depois.');
      if (st && st.temEntrar && cliques < 3) { await P.js(P.JS_CLICA_ENTRAR); cliques++; await _sleep(3000); continue; }
      if (ssoTent < SSO_PORTAL.length && !(st && st.mostraCpf)) { await P.vai(SSO_PORTAL[ssoTent++], 60000); continue; }
    } else if (HOST_PORTAL.test(u.host) && !/\/GIAM/i.test(u.pathname) && voltas < 4) {
      voltas++; await _sleep(1500); await P.vai(URL_GIAM, 45000); continue;
    }
    await _sleep(1500);
  }
  await _print();
  throw new Error('Não consegui abrir a 2ª via do recibo da GIAM no Portal do Contribuinte. O print da última tela ficou em "giam_ultima.png" e o passo a passo em "fisconforme_log.txt", na pasta de dados do FiscoCont+.');
}
async function _form() {
  let e = await _jsF(JS_ESTADO);
  for (let k = 0; k < 3 && !(e && e.r.form); k++) {
    if (e && e.r.bt2via) await _jsF(JS_CLICA_2VIA); else await P.vai(URL_GIAM, 45000);
    await _sleep(2000); e = await _espera(JS_ESTADO, 20000);
  }
  if (!(e && e.r.form)) { await _print(); throw new Error('o formulário da 2ª via do recibo não abriu'); }
  return e;
}

// ------------------------------------------------------------------ PDF do recibo
async function _salvaPdf(arq) {
  const w = P.win();
  const tipo = await w.webContents.executeJavaScript('document.contentType', true).catch(() => '');
  if (tipo === 'application/pdf') {
    const b64 = await w.webContents.executeJavaScript(`fetch(location.href).then((r) => r.arrayBuffer()).then((b) => { let s = ''; const u = new Uint8Array(b); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); })`, true);
    fs.writeFileSync(arq, Buffer.from(b64, 'base64'));
    return;
  }
  await _sleep(1200);
  fs.writeFileSync(arq, await w.webContents.printToPDF({ printBackground: true, pageSize: 'A4', margins: { marginType: 'default' } }));
}
// clica em "Imprimir Recibo" e salva o que abrir (nova janela, mesma janela ou download)
async function _imprimir(fr, i, arq) {
  const w = P.win();
  _abriu = null;
  const antes = w.webContents.getURL();
  let baixou = null;
  const ses = w.webContents.session;
  const onDown = (_ev, item) => { item.setSavePath(arq); item.once('done', (_e, st) => { baixou = st; }); };
  ses.once('will-download', onDown);
  try {
    const c = await _noFrame(fr, jsImprimir(i));
    if (c && c.erro) throw new Error(c.erro);
    const ate = Date.now() + 25000;
    while (Date.now() < ate) {
      await _sleep(500);
      if (baixou) { if (baixou !== 'completed') throw new Error('o download do recibo não terminou'); return; }
      if (_abriu) { const u = _abriu; _abriu = null; await P.vai(u, 45000); await _salvaPdf(arq); return; }
      if (w.webContents.getURL() !== antes) { await _sleep(1500); await _salvaPdf(arq); return; }
    }
    throw new Error('o recibo não abriu depois de "Imprimir Recibo"');
  } finally { ses.removeListener('will-download', onDown); }
}

// ------------------------------------------------------------------ pasta e empresas
const _nn = (s) => String(s || '').toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Z0-9]+/g, ' ').trim();
async function _cnpjs() {
  // IE → CNPJ/razão: a lista do portal (empresas do contador) e o que os Débitos e DARE já leram (dare/<ano>_<IE>)
  const m = new Map();
  _empsPortal.forEach((e) => { const x = e.t.match(/^(\d*)\s*-\s*(.+)$/); if (x && x[1]) m.set(_so(x[1]).replace(/^0+/, ''), { cnpj: e.cnpj, razao: x[2].trim() }); });
  const porNome = new Map();
  _empsPortal.forEach((e) => { const x = e.t.match(/^(\d*)\s*-\s*(.+)$/); const n = _nn(x ? x[2] : e.t); porNome.set(n, porNome.has(n) && porNome.get(n) !== e.cnpj ? '' : e.cnpj); });
  m.porNome = (nome) => porNome.get(_nn(nome)) || '';
  try { const { db, f } = _fs(); (await f.getDocs(f.collection(db, 'dare'))).forEach((d) => { const x = d.data() || {}; if (x.ie && x.cnpj && !m.has(_so(x.ie).replace(/^0+/, ''))) m.set(_so(x.ie).replace(/^0+/, ''), { cnpj: _so(x.cnpj), razao: x.razao || x.nome || '' }); }); } catch (_) {}
  return m;
}
function _destino(nome, cnpj, ie, comp) {
  const [a, mm] = comp.split('-');
  const arqNome = `Recibo GIAM SPED ${mm}${a} - IE ${_so(ie).replace(/^0+/, '')}.pdf`;
  const p = pastaCliente.achar({ nome, cnpj });
  if (p) {
    const dir = pastaCliente.pastaMes(p.dir, a, mm, true);
    if (dir) return { arq: path.join(dir, arqNome), dir, cliente: true, regime: p.regime || '' };
  }
  const dir = path.join(PASTA_AUTO, `${_limpaNome(nome)} - IE ${_so(ie).replace(/^0+/, '')}`, `${a}-${mm}`);
  return { arq: path.join(dir, arqNome), dir, cliente: false, regime: '' };
}

function _compMenos(comp, n) { const [a, m] = comp.split('-').map(Number); const d = new Date(a, m - 1 - n, 1); return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`; }
const _br = (d) => (/^\d{4}-\d{2}-\d{2}/.test(d || '') ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : '');
// referência da tabela: "202610" ou "10/2026" → "202610"
function _refAM(ref) { const d = _so(ref); if (/^20\d{4}$/.test(d)) return d; if (/^\d{2}20\d{2}$/.test(d)) return d.slice(2) + d.slice(0, 2); return d; }
async function _receita(cnpj, comp) {
  if (!cnpj || cnpj.length !== 14 || !D.cnpjApi) return null;
  const api = await D.cnpjApi(cnpj).catch(() => null);
  if (!api) return null;
  const [a, m] = comp.split('-').map(Number);
  const ini = `${comp}-01`, fim = `${comp}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}`;
  const op = String(api.data_opcao_pelo_simples || '').slice(0, 10), ex = String(api.data_exclusao_do_simples || '').slice(0, 10);
  const simples = op ? op <= fim && (!ex || ex > ini) : api.opcao_pelo_simples === true;
  const sit = _nn(api.descricao_situacao_cadastral || (typeof api.situacao_cadastral === 'string' ? api.situacao_cadastral : ''));
  const dtSit = String(api.data_situacao_cadastral || '').slice(0, 10);
  const inativa = /BAIXAD|INAPT|SUSPENS|NULA/.test(sit);
  return { simples, baixada: inativa && (!dtSit || dtSit < ini), inativa, sit, dtSit,
    info: simples ? `Simples Nacional${op ? ` desde ${_br(op)}` : ''} (Receita Federal)` : inativa ? `CNPJ ${sit.toLowerCase()}${dtSit ? ` em ${_br(dtSit)}` : ''} (Receita Federal)` : '' };
}

// consulta uma inscrição num período (AAAAMM a AAAAMM). nova = começa de uma página nova da 2ª via
async function _consulta(ie, perIni, perFim, nova) {
  if (nova) { await P.vai(URL_GIAM, 45000); await _sleep(800); }
  let res = null;
  for (let tent = 0; tent < 2 && !res; tent++) {
    const fm = await _form();
    const op = fm.r.ies.find((x) => _mesmaIE(x.t.split('-')[0], ie));
    if (!op) throw new Error('a inscrição saiu da lista');
    const r = await _noFrame(fm.fr, jsConsultar(op.v, perIni, perFim));
    if (r && r.erro) throw new Error(r.erro);
    await _sleep(1500);
    res = await _espera(JS_RES, 25000, 700);
    // sem tabela e sem mensagem reconhecida: não dá para afirmar nada (incerto)
    if (!res && (await _jsF(JS_ESTADO))) res = { r: { tabela: false, certo: false, msg: '' }, fr: fm.fr };
  }
  return res;
}

// ------------------------------------------------------------------ leitura de todas as inscrições
async function ler(comp, opc = {}) {
  _exige();
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(comp || '')) throw new Error('Competência inválida.');
  const per = comp.replace('-', '');
  P.ocupar(); _lendo = true; P.silencioso(!!opc.auto); P.limpaLog();
  const inicio = Date.now(), lid = new Date().toISOString();
  const ses = auth.sessao() || {};
  const { db, f } = _fs();
  try {
    let ies = await _entrar();
    if (opc.ie) ies = ies.filter((x) => _mesmaIE(x.t.split('-')[0], opc.ie));
    if (!ies.length) throw new Error(opc.ie ? 'Essa inscrição não está na lista da GIAM do contador.' : 'A lista de inscrições da GIAM veio vazia no portal.');
    const cnpjs = await _cnpjs();
    const cont = { processado: 0, nao_processado: 0, simples: 0, baixada: 0, sem_entregas: 0, erro: 0, retif: 0 };
    for (let i = 0; i < ies.length; i++) {
      const m = ies[i].t.match(/^(\d{8,14})\s*-\s*(.+)$/);
      const ie = m ? m[1] : _so(ies[i].t), nome = m ? m[2].trim() : ies[i].t;
      const info = cnpjs.get(_so(ie).replace(/^0+/, '')) || {};
      _prog(`Recibo GIAM/SPED ${comp.slice(5, 7)}/${comp.slice(0, 4)} · ${i + 1} de ${ies.length} · ${nome}`, { i: i + 1, n: ies.length });
      const dest = _destino(info.razao || nome, info.cnpj, ie, comp);
      let doc = { ie, nome, cnpj: info.cnpj || '', comp, regime: dest.regime, lidoEm: lid, erro: '' };
      try {
        let res = await _consulta(ie, per, per, false);
        let linhas = res && res.r.tabela ? res.r.linhas.filter((l) => _refAM(l.ref) === per) : [];
        let ultimaRef = '', semNada = false;
        if (!linhas.length) {
          // confere numa página nova antes de dizer que não tem (resultado de página antiga, lentidão do portal)
          res = await _consulta(ie, per, per, true);
          linhas = res && res.r.tabela ? res.r.linhas.filter((l) => _refAM(l.ref) === per) : [];
          if (!linhas.length) {
            const r12 = await _consulta(ie, _compMenos(comp, 12), per, true).catch(() => null);
            const l12 = r12 && r12.r.tabela ? r12.r.linhas : [];
            if (l12.some((l) => _refAM(l.ref) === per)) { res = r12; linhas = l12.filter((l) => _refAM(l.ref) === per); }
            else if (l12.length) ultimaRef = l12.map((l) => _refAM(l.ref)).sort().pop();
            else semNada = !!(r12 && !r12.r.tabela && r12.r.certo);
            P.log(`GIAM ${ie}: últimos 12 meses · ${l12.length ? `${l12.length} entrega(s), última ref. ${ultimaRef}` : semNada ? 'nenhuma entrega' : 'resultado incerto'}`);
          }
        }
        if (linhas.length) {
          // retificadora: o recibo da última entrega
          const dt = (s) => { const x = String(s).match(/(\d{2})\/(\d{2})\/(\d{4})/); return x ? `${x[3]}${x[2]}${x[1]}` : ''; };
          const ult = linhas.slice().sort((a, b) => dt(a.entrega).localeCompare(dt(b.entrega)))[linhas.length - 1];
          fs.mkdirSync(dest.dir, { recursive: true });
          await _imprimir(res.fr, ult.i, dest.arq);
          doc = { ...doc, status: 'processado', entrega: ult.entrega, retificadora: /SIM/i.test(ult.retif), entregas: linhas.map((l) => ({ entrega: l.entrega, retificadora: /SIM/i.test(l.retif) })),
            arquivo: dest.arq, cliente: dest.cliente, pasta: dest.dir };
          cont.processado++; if (doc.retificadora) cont.retif++;
          P.log(`GIAM ${ie} ${nome}: recibo de ${ult.entrega}${doc.retificadora ? ' (retificadora)' : ''} salvo em ${dest.arq}`);
          await P.vai(URL_GIAM, 45000);                         // volta para a 2ª via
        } else {
          const cnpj = info.cnpj || cnpjs.porNome(nome);
          const rec = await _receita(cnpj, comp);
          let status = 'nao_processado', msg = (res && res.r.msg) || '';
          if (/simples/i.test(dest.regime) || (rec && rec.simples)) { status = 'simples'; msg = rec && rec.simples ? rec.info : 'pasta do Simples Nacional'; }
          else if (rec && rec.baixada) { status = 'baixada'; msg = rec.info; }
          else if (semNada) { status = 'sem_entregas'; msg = 'nenhuma GIAM/SPED entregue nos últimos 12 meses: inscrição provavelmente baixada ou sem obrigação'; }
          else if (rec && rec.inativa) msg = rec.info;
          doc = { ...doc, cnpj: cnpj || doc.cnpj, status, msg, ultimaRef };
          cont[status] = (cont[status] || 0) + 1;
          P.log(`GIAM ${ie} ${nome}: sem recibo de ${per} → ${status}${msg ? ` (${msg})` : ''}`);
        }
      } catch (e) {
        cont.erro++; P.log(`GIAM ${ie} ${nome}: ${e.message || e}`); await _print();
        doc = { ...doc, status: 'erro', erro: String(e.message || e).slice(0, 200) };
        await P.vai(URL_GIAM, 45000).catch(() => {});
      }
      await f.setDoc(f.doc(db, COL, `${comp}_${_so(ie).replace(/^0+/, '')}`), doc, { merge: false });
      try { D.notificar('giam:empresa', { comp, ie }); } catch (_) {}
    }
    const meta = { ultimaLeitura: lid, por: opc.auto ? 'Verificação automática' : (ses.nome || ses.email || ''), auto: !!opc.auto, comp, duracaoSeg: Math.round((Date.now() - inicio) / 1000) };
    if (!opc.ie) Object.assign(meta, { empresas: ies.length, ...cont });
    await f.setDoc(f.doc(db, COL, `_meta_${comp}`), meta, { merge: true });
    _prog('', { fim: true });
    return { ok: true, ...meta, ...cont };
  } catch (e) {
    P.log(`GIAM: parou · ${e.message || e}`); _prog('', { fim: true });
    throw e;
  } finally { _lendo = false; P.silencioso(false); P.liberar(true); }
}

async function dados(comp) {
  _exige();
  const { db, f } = _fs();
  const emps = [];
  (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).forEach((d) => emps.push(d.data()));
  const m = await f.getDoc(f.doc(db, COL, `_meta_${comp}`)).catch(() => null);
  return { comp, emps, meta: m && m.exists() ? m.data() : null, rodando: _lendo };
}
const ocupado = () => _lendo;

module.exports = { init, podeUsar, ler, dados, compAnterior, ocupado, MODULO };
