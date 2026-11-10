'use strict';
// Débitos e DARE · SEFIN-RO (Portal do Contribuinte).
//
// • Consulta os débitos em aberto do exercício (padrão: o ano vigente) de TODAS as empresas que aparecem na lista de
//   Inscrições Estaduais da tela "Consulta Débitos em Aberto", com o e-CPF do contador (mesma entrada do Fisconforme).
// • Gera o DARE para a data de pagamento escolhida e baixa o extrato do lançamento, salvando na pasta da empresa:
//     <pasta>\<NOME DA EMPRESA> - IE <IE>\DARE ICMS <receita> Nº <lançamento> - <NOME DA EMPRESA>.pdf
//     <pasta>\<NOME DA EMPRESA> - IE <IE>\Extrato Ref DARE ICMS <receita> Nº <lançamento> - <NOME DA EMPRESA>.pdf
// • A emissão do DARE fica no site dare.sefin.ro.gov.br. Quando a SEFIN pede o código de segurança (captcha), a imagem vai
//   para a tela e quem está gerando digita. O sistema nunca tenta ler ou resolver esse código.
// • Guarda os débitos na nuvem (coleção dare: um documento por exercício + IE, com os DAREs já gerados).

const fs = require('fs');
const path = require('path');
const auth = require('./auth');
const fisc = require('./fisconforme');

const P = fisc.portal;
const URL_CONSULTA = 'https://portalcontribuinte.sefin.ro.gov.br/app/consultadebitos/';
const HOST_PORTAL = /(^|\.)portalcontribuinte\.sefin\.ro\.gov\.br$/i;
const SSO_PORTAL = [
  'https://sitafesec-sso-int.sefin.ro.gov.br/acesso_externo/acesso_digital?request_url='
    + encodeURIComponent('http://portalcontribuinte.sefin.ro.gov.br/SsoLogin') + '&login_template=default',
  'https://sitafesec-sso-int.sefin.ro.gov.br/acesso_externo/acesso_digital?request_url='
    + encodeURIComponent('https://portalcontribuinte.sefin.ro.gov.br/app/consultadebitos/') + '&login_template=default',
];
const COL = 'dare';
const PASTA_PADRAO = 'G:\\Drives compartilhados\\Fiscal - Lucro Real\\00 - Arquivos FISCAL\\DARES Automáticos';
const MODULO = 'fiscal-dare';

let D = null;                 // { userData, notificar(canal, dados) }
let _abriu = null;            // URL que o portal tentou abrir em nova janela (o link "Emitir")
let _prep = null;             // DARE aberto esperando a data e o código: { ie, nr, parc, ano, nome, rec, fr, ate }
let _relogio = null;

function init(deps) { D = deps; }

function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes(MODULO) : s.perfil === 'fiscal';
}
function _exige() { if (!podeUsar()) throw new Error('Sem acesso ao módulo Débitos e DARE.'); }
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');
function _prog(txt, extra) { try { D.notificar('dare:progresso', { txt, ...(extra || {}) }); } catch (_) {} }
const _num = (v) => { const n = parseFloat(String(v || '').replace(/\./g, '').replace(',', '.')); return Number.isFinite(n) ? n : 0; };
const _limpaNome = (s) => String(s || '').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '');
const pasta = () => (P.cfg().pastaDare || PASTA_PADRAO);

// ------------------------------------------------------------------ janela (a mesma do Fisconforme)
// A página do DARE da SEFIN chama a impressão sozinha quando abre (window.print), o que mostraria a janela de
// impressoras do Windows. Antes de qualquer página carregar, o sistema troca essa chamada por nada: o PDF é salvo direto.
const SEM_IMPRESSAO = 'try { window.print = function () {}; } catch (e) {}';
async function _janela() {
  const w = P.janela();
  if (!w.__dare) {
    w.__dare = true;
    // links que abrem nova aba (o "Emitir" do DARE, por exemplo): guarda o endereço e abre na mesma janela
    w.webContents.setWindowOpenHandler(({ url }) => { _abriu = url; P.log(`nova janela pedida: ${String(url).split('?')[0]}`); return { action: 'deny' }; });
    try {
      const dbg = w.webContents.debugger;
      if (!dbg.isAttached()) dbg.attach('1.3');
      await dbg.sendCommand('Page.enable');
      await dbg.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: SEM_IMPRESSAO, runImmediately: true });
    } catch (e) { P.log(`aviso: não consegui desligar a impressão automática (${e.message || e})`); }
    // reforço: a cada página carregada, desliga de novo em todos os frames
    w.webContents.on('dom-ready', () => { try { w.webContents.mainFrame.framesInSubtree.forEach((fr) => fr.executeJavaScript(SEM_IMPRESSAO).catch(() => {})); } catch (_) {} });
  }
  return w;
}
// roda o código em todos os frames da página e devolve o primeiro resultado útil (o portal antigo usa frames)
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
async function _espera(code, ms, passo = 700) {
  const ate = Date.now() + ms;
  while (Date.now() < ate) { const x = await _jsF(code); if (x) return x; await _sleep(passo); }
  return null;
}
async function _print(nome) {
  try { const img = await P.win().webContents.capturePage(); fs.writeFileSync(path.join(D.userData(), nome), img.toPNG()); } catch (_) {}
}

// ------------------------------------------------------------------ scripts das páginas
const JS_LIMPA = 'const limpa = (s) => String(s == null ? "" : s).replace(/\\s+/g, " ").trim();';
const JS_SEL_IE = `const selIE = () => [...document.querySelectorAll('select')].find((s) => [...s.options].some((o) => /^\\s*\\d{8,14}\\s*-\\s*\\S/.test(o.textContent)));`;

const JS_FORM = `(() => { ${JS_LIMPA} ${JS_SEL_IE}
  const s = selIE(); if (!s) return null;
  const ies = [...s.options].map((o) => ({ v: o.value, t: limpa(o.textContent) })).filter((o) => /^\\d{8,14}\\s*-/.test(o.t));
  return ies.length ? { ies } : null; })()`;

const jsConsultar = (v, ano) => `(() => { ${JS_SEL_IE}
  const s = selIE(); if (!s) return { erro: 'a lista de inscrições não apareceu' };
  const setv = (el, val) => { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  if (s.value !== ${JSON.stringify(v)}) setv(s, ${JSON.stringify(v)});
  const ins = [...document.querySelectorAll('input')].filter((i) => !i.type || /^(text|number|tel|search)$/i.test(i.type));
  const ano = ins.find((i) => /ano|exerc/i.test((i.name || '') + ' ' + (i.id || ''))) || ins.find((i) => /^\\d{4}$/.test(i.value));
  if (ano) setv(ano, ${JSON.stringify(String(ano))});
  const b = [...document.querySelectorAll('input[type=submit], input[type=button], button, a')].find((x) => /consultar\\s+d[eé]bitos/i.test(x.value || x.innerText || ''));
  if (!b) return { erro: 'o botão Consultar Débitos não apareceu' };
  b.click(); return { ok: true, ano: !!ano }; })()`;

// acha o cabeçalho "Dare | Extrato | Nr. Lançamento | ..." e as linhas da tabela de débitos
const JS_TABELA = `${JS_LIMPA}
  const tabela = () => {
    const hd = [...document.querySelectorAll('tr')].find((tr) => { const t = limpa(tr.innerText); return /Nr\\.?\\s*Lan[cç]amento/i.test(t) && /Receita/i.test(t) && tr.children.length >= 6; });
    if (!hd) return null;
    const nomes = [...hd.children].map((c) => limpa(c.innerText).toLowerCase());
    const col = (re) => nomes.findIndex((n) => re.test(n));
    const C = { dare: col(/^dare/), ext: col(/^extrato/), nr: col(/lan[cç]amento/), parc: col(/^parc/), ref: col(/refer/), comp: col(/complem/),
      rec: col(/receita/), sit: col(/situa/), venc: col(/venc/), val: col(/valor\\s*lan/), atu: col(/atualiz/) };
    const pai = hd.parentElement;
    const corpo = pai.tagName === 'THEAD' ? [...hd.closest('table').tBodies].flatMap((b) => [...b.rows]) : [...pai.children].slice([...pai.children].indexOf(hd) + 1);
    return { hd, C, nomes, corpo };
  };`;

const JS_RESULTADO = `(() => { ${JS_TABELA}
  const txt = document.body ? document.body.innerText : '';
  const cab = { cnpj: (txt.match(/C\\.N\\.P\\.J:?\\s*([\\d./-]{14,18})/) || [])[1] || '', razao: limpa((txt.match(/Raz[aã]o Social:?\\s*([^\\n]+)/) || [])[1]),
    ie: (txt.match(/Inscri[cç][aã]o Estadual:?\\s*(\\d{8,14})/) || [])[1] || '' };
  const T = tabela();
  if (!T) {
    if (/LISTA DE D[EÉ]BITOS/i.test(txt) || /(n[aã]o (foram encontrad|h[aá]|exist|possui)|nenhum)[^\\n]{0,40}d[eé]bito/i.test(txt))
      return { pronto: true, linhas: [], cab, msg: limpa(txt).slice(0, 300) };
    return null;
  }
  const linhas = [];
  T.corpo.forEach((r) => {
    const td = [...r.children]; if (td.length < 6) return;
    const g = (k) => (T.C[k] >= 0 && td[T.C[k]] ? limpa(td[T.C[k]].innerText) : '');
    const nr = g('nr'); if (!/^\\d{6,}$/.test(nr)) return;
    const lk = (k) => !!(T.C[k] >= 0 && td[T.C[k]] && td[T.C[k]].querySelector('a, button, input[type=button]'));
    linhas.push({ nr, parc: g('parc'), ref: g('ref'), comp: g('comp'), rec: g('rec'), sit: g('sit'), venc: g('venc'), valor: g('val'), valorAtu: g('atu'),
      temDare: lk('dare'), temExt: lk('ext') });
  });
  return { pronto: true, linhas, cab }; })()`;

const jsClica = (nr, parc, qual) => `(() => { ${JS_TABELA}
  const T = tabela(); if (!T) return { erro: 'a tabela de débitos não apareceu' };
  const i = T.C[${JSON.stringify(qual)}]; if (i < 0) return { erro: 'coluna não encontrada' };
  const r = T.corpo.find((tr) => { const td = [...tr.children]; return td[T.C.nr] && limpa(td[T.C.nr].innerText) === ${JSON.stringify(nr)}
    && (T.C.parc < 0 || limpa(td[T.C.parc].innerText) === ${JSON.stringify(parc)}); });
  if (!r) return { erro: 'o lançamento não está mais na lista' };
  const a = r.children[i] && r.children[i].querySelector('a, button, input[type=button]');
  if (!a) return { erro: 'o portal não oferece esse documento para o lançamento' };
  a.click(); return { ok: true }; })()`;

// tela de emissão (dare.sefin.ro.gov.br): data de pagamento, código de segurança e botão EMITIR
const JS_CAP = `
  const vis = (e) => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const capEl = () => {
    let el = [...document.querySelectorAll('img, canvas')].filter(vis).find((i) => /captcha/i.test([i.src, i.alt, i.id, i.className, i.getAttribute('name')].join(' ')));
    if (el) return el;
    const rot = [...document.querySelectorAll('label, span, div, td, th, p, b, strong')].find((x) => /^\\s*captcha\\s*:?\\s*$/i.test(x.innerText || ''));
    let box = rot; for (let k = 0; k < 5 && box; k++) { box = box.parentElement; const c = box && [...box.querySelectorAll('img, canvas')].filter(vis)[0]; if (c) return c; }
    return null;
  };
  const capInput = () => {
    const el = capEl();
    const porNome = [...document.querySelectorAll('input')].filter(vis).find((i) => /captcha|codigo|seguran/i.test([i.name, i.id, i.placeholder, i.getAttribute('formcontrolname')].join(' ')));
    if (porNome) return porNome;
    let box = el; for (let k = 0; k < 5 && box; k++) { box = box.parentElement; const i = box && [...box.querySelectorAll('input')].filter(vis).find((x) => !x.type || /text/i.test(x.type)); if (i) return i; }
    return null;
  };
  const dataSel = () => [...document.querySelectorAll('select')].filter(vis).find((s) => [...s.options].some((o) => /\\d{2}\\/\\d{2}\\/\\d{4}/.test(o.textContent)));
  const dataInp = () => [...document.querySelectorAll('input')].filter(vis).find((i) => /^\\d{2}\\/\\d{2}\\/\\d{4}$/.test(i.value) || /data|pagamento/i.test([i.name, i.id, i.getAttribute('formcontrolname')].join(' ')));
`;
const JS_DARE_FORM = `(() => { ${JS_LIMPA} ${JS_CAP}
  const txt = document.body ? document.body.innerText : '';
  if (!/data\\s+de\\s+pagamento/i.test(txt)) return null;
  const s = dataSel(), di = s ? null : dataInp();
  const datas = s ? [...s.options].map((o) => limpa(o.textContent)).filter((t) => /^\\d{2}\\/\\d{2}\\/\\d{4}$/.test(t)) : [];
  const atual = s ? limpa((s.options[s.selectedIndex] || {}).textContent) : (di ? di.value : '');
  return { datas, atual, livre: !s && !!di, temCaptcha: !!capEl() }; })()`;

// imagem do código de segurança como dataURL (desenha a imagem já carregada, sem buscar outra)
const JS_CAP_IMG = `(() => { ${JS_CAP}
  const el = capEl(); if (!el) return { nenhum: true };
  try {
    if (el.tagName === 'CANVAS') return { url: el.toDataURL('image/png') };
    if (/^data:/.test(el.src)) return { url: el.src };
    const c = document.createElement('canvas'); c.width = el.naturalWidth || el.width; c.height = el.naturalHeight || el.height;
    c.getContext('2d').drawImage(el, 0, 0); return { url: c.toDataURL('image/png') };
  } catch (e) { const r = el.getBoundingClientRect(); return { rect: { x: Math.floor(r.x), y: Math.floor(r.y), width: Math.ceil(r.width), height: Math.ceil(r.height) } }; }
})()`;
const JS_CAP_NOVO = `(() => { ${JS_CAP}
  const el = capEl(); if (!el) return false;
  let box = el; for (let k = 0; k < 4 && box; k++) { box = box.parentElement; const b = box && [...box.querySelectorAll('button, a, i, span')].filter(vis).find((x) => x !== el && !/emitir/i.test(x.innerText || '') && (x.tagName === 'BUTTON' || /refresh|reload|atualiz|recarreg|sync|redo/i.test([x.className, x.title, x.getAttribute('aria-label')].join(' ')))); if (b) { b.click(); return true; } }
  return false; })()`;

const jsEmitir = (data, codigo) => `(() => { ${JS_LIMPA} ${JS_CAP}
  window.__alerta = ''; window.alert = (m) => { window.__alerta = String(m); }; window.print = function () {};
  const setv = (el, v) => { const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value'); if (d && d.set) d.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); };
  const s = dataSel();
  if (s) { const o = [...s.options].find((x) => limpa(x.textContent) === ${JSON.stringify(data)}); if (!o) return { erro: 'essa data não está disponível no portal' }; setv(s, o.value); }
  else { const di = dataInp(); if (di) setv(di, ${JSON.stringify(data)}); }
  const ci = capInput();
  ${codigo == null ? '' : `if (!ci) return { erro: 'o campo do código de segurança não apareceu' }; setv(ci, ${JSON.stringify(String(codigo))});`}
  const b = [...document.querySelectorAll('button, input[type=submit], input[type=button], a')].filter(vis).find((x) => /^\\s*emitir\\s*$/i.test(x.innerText || x.value || ''));
  if (!b) return { erro: 'o botão EMITIR não apareceu' };
  b.click(); return { ok: true }; })()`;

const JS_POS_EMITIR = `(() => { ${JS_LIMPA}
  const txt = document.body ? document.body.innerText : '';
  if (/DOCUMENTO DE ARRECADA/i.test(txt) && /Valor Total/i.test(txt)) return { doc: true };
  if (document.contentType === 'application/pdf') return { pdf: true };
  const al = window.__alerta || '';
  const err = [...document.querySelectorAll('.alert, .error, .erro, .invalid-feedback, .toast, .swal2-html-container, .mat-error, [role=alert]')]
    .map((e) => limpa(e.innerText)).filter((t) => t && t.length < 300).join(' · ');
  const m = al || err;
  if (m) return { erro: m, captcha: /captcha|c[oó]digo|seguran|caracter/i.test(m) };
  return null; })()`;

const JS_DARE_DADOS = `(() => { ${JS_LIMPA}
  const t = document.body ? document.body.innerText : '';
  const v = (re) => ((t.match(re) || [])[1] || '').trim();
  return { total: v(/13\\s*-\\s*Valor Total\\s*([\\d.]+,\\d{2})/i), ateDia: v(/PAGAMENTO AT[EÉ] O DIA\\s*(\\d{2}\\/\\d{2}\\/\\d{4})/i),
    linha: v(/(\\d{11,12}\\s\\d{11,12}\\s\\d{11,12}\\s\\d{11,12})/), venc: v(/Data Vencimento\\s*(\\d{2}\\/\\d{2}\\/\\d{4})/i) }; })()`;

// ------------------------------------------------------------------ entrada no Portal do Contribuinte
async function _entrar() {
  P.canal('dare:progresso');
  _prog('Entrando no portal da SEFIN com o certificado do contador…');
  await P.loginSso();                                  // mesma entrada do Fisconforme (sessão do SSO)
  await _janela();
  _prog('Abrindo o Portal do Contribuinte…');
  await P.vai(URL_CONSULTA, 45000);
  const ate = Date.now() + 100000;
  let ssoTent = 0, cliques = 0, voltas = 0, ult = '';
  while (Date.now() < ate) {
    const f = await _jsF(JS_FORM);
    if (f) { P.log(`consulta de débitos aberta: ${f.r.ies.length} inscrição(ões) na lista`); return f.r.ies; }
    const u = new URL(P.win().webContents.getURL() || 'about:blank');
    if (P.ehSso(u.host)) {
      const st = await P.js(P.JS_ESTADO_LOGIN).catch(() => null);
      if (st && st.texto !== ult) { P.log(`SSO (portal): ${st.texto}`); ult = st.texto; }
      if (st && st.captcha) throw new Error('O portal pediu captcha na entrada e a consulta parou. Entre uma vez pelo navegador e tente de novo depois.');
      if (st && st.temEntrar && cliques < 3) { await P.js(P.JS_CLICA_ENTRAR); cliques++; P.log('clicou em Entrar'); await _sleep(3000); continue; }
      if (ssoTent < SSO_PORTAL.length && !(st && st.mostraCpf)) { P.log(`tentando a entrada por certificado (${ssoTent + 1})`); await P.vai(SSO_PORTAL[ssoTent++], 60000); continue; }
    } else if (HOST_PORTAL.test(u.host) && !/consultadebitos/i.test(u.pathname) && voltas < 4) {
      voltas++; await _sleep(1500); await P.vai(URL_CONSULTA, 45000); continue;
    }
    await _sleep(1500);
  }
  await _print('dare_login.png');
  if (!P.ehAdmin()) throw new Error('Não consegui abrir a consulta de débitos no portal. Tente de novo em alguns minutos; se continuar, avise o Admin.');
  throw new Error('Não consegui abrir a consulta de débitos no Portal do Contribuinte. Ligue "Mostrar a janela da consulta" no Fisconforme e tente de novo para ver onde parou. '
    + 'O print da última tela e o passo a passo ficaram em "dare_login.png" e "fisconforme_log.txt", na pasta de dados do FiscoCont+.');
}

// abre a consulta e pesquisa uma inscrição no exercício; devolve a tabela lida
async function _consultar(ie, ano) {
  let f = await _jsF(JS_FORM);
  if (!f) { await P.vai(URL_CONSULTA, 45000); f = await _espera(JS_FORM, 30000); }
  if (!f) throw new Error('a tela de consulta não abriu');
  const op = f.r.ies.find((x) => x.t.startsWith(ie)) || f.r.ies.find((x) => _so(x.t.split('-')[0]) === _so(ie));
  if (!op) throw new Error('a inscrição não está na lista do contador');
  const r = await _noFrame(f.fr, jsConsultar(op.v, ano));
  if (r && r.erro) throw new Error(r.erro);
  await _sleep(1200);
  const res = await _espera(JS_RESULTADO, 35000, 800);
  if (!res) throw new Error('o portal não devolveu a lista de débitos');
  if (res.r.cab.ie && _so(res.r.cab.ie) !== _so(ie)) throw new Error(`o portal mostrou outra inscrição (${res.r.cab.ie})`);
  return res;
}

// clica num link da tabela (Dare ou Extrato) e espera o destino abrir nesta janela
async function _abrirLink(res, nr, parc, qual) {
  _abriu = null;
  const antes = P.win().webContents.getURL();
  const c = await _noFrame(res.fr, jsClica(nr, parc, qual));
  if (c && c.erro) throw new Error(c.erro);
  const ate = Date.now() + 20000;
  while (Date.now() < ate) {
    await _sleep(500);
    if (_abriu) { const u = _abriu; _abriu = null; await P.vai(u, 45000); return; }
    if (P.win().webContents.getURL() !== antes) { await _sleep(1500); return; }
  }
  // alguns links trocam só o conteúdo do frame: segue com a página atual
}

// ------------------------------------------------------------------ consulta de todas as empresas
let _lendo = false;
async function ler(ano, opc = {}) {
  _exige();
  ano = String(ano || new Date().getFullYear());
  P.ocupar(); _lendo = true; P.silencioso(!!opc.auto);
  P.limpaLog();
  const inicio = Date.now(), lid = new Date().toISOString();
  try {
    const ies = await _entrar();
    if (!ies.length) throw new Error('A lista de inscrições do contador veio vazia no portal.');
    const { db, f } = _fs();
    const ses = auth.sessao() || {};
    let comDebito = 0, total = 0, falhas = 0;
    // débitos já conhecidos (para contar os novos desta consulta)
    const conhecidos = new Set();
    (await f.getDocs(f.collection(db, COL))).forEach((d) => { if (d.id.startsWith(`${ano}_`)) (d.data().debitos || []).forEach((l) => conhecidos.add(`${d.data().ie}|${l.nr}|${l.parc}`)); });
    const primeira = conhecidos.size === 0;
    let novos = 0, novosValor = 0;
    const novosEmp = {};
    const vencs = [];                                  // resumo leve para o número do menu: vencimento + valor de cada débito
    for (let i = 0; i < ies.length; i++) {
      const m = ies[i].t.match(/^(\d{8,14})\s*-\s*(.+)$/);
      const ie = m ? m[1] : _so(ies[i].t), nome = m ? m[2].trim() : ies[i].t;
      _prog(`Consultando ${i + 1} de ${ies.length} · ${nome}`, { i: i + 1, n: ies.length });
      let doc;
      try {
        let res;
        try { res = await _consultar(ie, ano); } catch (e1) { P.log(`${ie}: ${e1.message} · tentando de novo`); await P.vai(URL_CONSULTA, 45000); res = await _consultar(ie, ano); }
        const linhas = res.r.linhas.map((l) => ({ ...l, valorN: _num(l.valor), valorAtuN: _num(l.valorAtu) }));
        doc = { ie, nome, razao: res.r.cab.razao || nome, cnpj: _so(res.r.cab.cnpj), ano, debitos: linhas, lidoEm: lid, erro: '' };
        if (linhas.length) { comDebito++; total += linhas.reduce((s, l) => s + l.valorN, 0); }
        linhas.forEach((l) => { if (!conhecidos.has(`${ie}|${l.nr}|${l.parc}`)) { novos++; novosValor += l.valorN; novosEmp[nome] = (novosEmp[nome] || 0) + 1; } });
        linhas.forEach((l) => vencs.push({ v: l.venc, x: l.valorN }));
        P.log(`${ie} ${nome}: ${linhas.length} débito(s)`);
      } catch (e) {
        falhas++; P.log(`${ie} ${nome}: ${e.message || e}`);
        doc = { ie, nome, ano, lidoEm: lid, erro: String(e.message || e).slice(0, 200) };
      }
      await f.setDoc(f.doc(db, COL, `${ano}_${ie}`), doc, { merge: true });
      await P.vai(URL_CONSULTA, 45000);
    }
    const resumo = { ultimaLeitura: lid, por: opc.auto ? 'Consulta automática' : (ses.nome || ses.email || ''), auto: !!opc.auto,
      novos: primeira ? 0 : novos, novosValor: primeira ? 0 : Math.round(novosValor * 100) / 100,
      novosEmp: primeira ? [] : Object.entries(novosEmp).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([nome, n]) => ({ nome, n })), ano, empresas: ies.length, comDebito, total: Math.round(total * 100) / 100,
      falhas, duracaoSeg: Math.round((Date.now() - inicio) / 1000), contador: { nome: P.cfg().nome || '' }, vencs };
    await f.setDoc(f.doc(db, COL, `_meta_${ano}`), resumo, { merge: true });
    _prog('', { fim: true });
    return { ok: true, ...resumo };
  } catch (e) {
    P.log(`débitos: parou · ${e.message || e}`); _prog('', { fim: true });
    throw e;
  } finally { _lendo = false; P.silencioso(false); P.liberar(true); }
}

// resumo para o cartão do menu: só o _meta do exercício (vencimentos e valores, sem as empresas)
async function resumo(ano) {
  _exige();
  ano = String(ano || new Date().getFullYear());
  const { db, f } = _fs();
  const m = (await f.getDoc(f.doc(db, COL, `_meta_${ano}`))).data() || null;
  if (!m) return { vencs: null };
  const info = { ultimaLeitura: m.ultimaLeitura || '', novos: m.novos || 0, novosValor: m.novosValor || 0, novosEmp: m.novosEmp || [] };
  if (Array.isArray(m.vencs)) return { vencs: m.vencs, ...info };
  // consulta feita antes desta versão: monta a partir das empresas
  const vencs = [];
  (await f.getDocs(f.collection(db, COL))).forEach((d) => { if (d.id.startsWith(`${ano}_`)) (d.data().debitos || []).forEach((l) => vencs.push({ v: l.venc, x: l.valorN || 0 })); });
  return { vencs, ...info };
}

async function dados(ano) {
  _exige();
  ano = String(ano || new Date().getFullYear());
  const { db, f } = _fs();
  const emps = [];
  let meta = null;
  (await f.getDocs(f.collection(db, COL))).forEach((d) => {
    if (d.id === `_meta_${ano}`) meta = d.data();
    else if (d.id.startsWith(`${ano}_`)) emps.push(d.data());
  });
  return { ano, emps, meta, pasta: pasta(), rodando: _lendo || !!_prep };
}

// ------------------------------------------------------------------ nomes e pasta da empresa
function _nomes(x) {
  const emp = _limpaNome(x.nome);
  const tipo = /^1\d{3}$/.test(x.rec) ? `ICMS ${x.rec}` : `${x.rec}`;
  const parc = x.parc && !/^0+$/.test(x.parc) ? ` Parcela ${x.parc}` : '';
  const dir = path.join(pasta(), `${emp} - IE ${x.ie}`);
  return { dir, dare: path.join(dir, `DARE ${tipo} Nº ${x.nr}${parc} - ${emp}.pdf`), extrato: path.join(dir, `Extrato Ref DARE ${tipo} Nº ${x.nr}${parc} - ${emp}.pdf`) };
}
function _garantePasta(dir) {
  const raiz = pasta();
  if (!fs.existsSync(raiz)) throw new Error(`Não encontrei a pasta "${raiz}" neste computador. Confira se o Google Drive está aberto e com o drive G: disponível.`);
  fs.mkdirSync(dir, { recursive: true });
}
function previa(x) { _exige(); return { ok: true, ..._nomes(x) }; }

async function _salvaPdf(arq, landscape) {
  const w = P.win();
  const ehPdf = await w.webContents.executeJavaScript('document.contentType', true).catch(() => '');
  if (ehPdf === 'application/pdf') {
    const b64 = await w.webContents.executeJavaScript(`fetch(location.href).then((r) => r.arrayBuffer()).then((b) => { let s = ''; const u = new Uint8Array(b); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); })`, true);
    fs.writeFileSync(arq, Buffer.from(b64, 'base64'));
    return;
  }
  await _sleep(1200);
  const buf = await w.webContents.printToPDF({ printBackground: true, pageSize: 'A4', landscape: !!landscape, margins: { marginType: 'default' } });
  fs.writeFileSync(arq, buf);
}

async function _marca(x, campos) {
  const { db, f } = _fs();
  const k = `${x.nr}_${x.parc || '00'}`;
  await f.setDoc(f.doc(db, COL, `${x.ano}_${x.ie}`), { gerados: { [k]: campos } }, { merge: true });
}

// ------------------------------------------------------------------ extrato (sem código de segurança)
async function _baixarExtrato(x) {
  const n = _nomes(x);
  _garantePasta(n.dir);
  _prog(`Baixando o extrato do lançamento ${x.nr}…`);
  await P.vai(URL_CONSULTA, 45000);
  const res = await _consultar(x.ie, x.ano);
  await _abrirLink(res, x.nr, x.parc, 'ext');
  const ok = await _espera(`(() => /Extrato (do Conta Corrente|de Lan)/i.test(document.body ? document.body.innerText : '') || null)()`, 30000);
  if (!ok) throw new Error('o extrato não abriu no portal');
  await _salvaPdf(n.extrato, true);
  return n.extrato;
}
async function extrato(x) {
  _exige();
  P.ocupar(); P.limpaLog();
  try {
    await _entrar();
    const arq = await _baixarExtrato(x);
    const ses = auth.sessao() || {};
    await _marca(x, { extrato: arq, extratoEm: new Date().toISOString(), extratoPor: ses.nome || ses.email || '' });
    _prog('', { fim: true });
    return { ok: true, arquivo: arq };
  } catch (e) { P.log(`extrato ${x.nr}: ${e.message || e}`); _prog('', { fim: true }); throw e; }
  finally { P.liberar(true); }
}

// ------------------------------------------------------------------ DARE: 1) abre e devolve as datas e o código; 2) emite
function _fechaPrep() {
  if (_relogio) { clearTimeout(_relogio); _relogio = null; }
  _prep = null; P.liberar(true);
}
function _armaRelogio() {
  if (_relogio) clearTimeout(_relogio);
  _relogio = setTimeout(() => { P.log('DARE: tempo esgotado esperando a data e o código'); _fechaPrep(); }, 5 * 60 * 1000);
}
async function _imgCodigo() {
  const c = await _jsF(JS_CAP_IMG);
  if (!c || c.r.nenhum) return null;
  if (c.r.url) return c.r.url;
  try { const img = await P.win().webContents.capturePage(c.r.rect); return img.toDataURL(); } catch (_) { return null; }
}

async function preparar(x) {
  _exige();
  if (_prep) _fechaPrep();
  P.ocupar(); P.limpaLog();
  try {
    await _entrar();
    _prog(`Abrindo o DARE do lançamento ${x.nr}…`);
    const res = await _consultar(x.ie, x.ano);
    await _abrirLink(res, x.nr, x.parc, 'dare');
    const fm = await _espera(JS_DARE_FORM, 40000, 800);
    if (!fm) { await _print('dare_emissao.png'); throw new Error('a tela de emissão do DARE não abriu'); }
    const img = fm.r.temCaptcha ? await _imgCodigo() : null;
    _prep = { ...x, fr: fm.fr };
    _armaRelogio();
    _prog('', { fim: true });
    P.log(`DARE ${x.nr}: ${fm.r.datas.length} data(s) disponível(is)${fm.r.temCaptcha ? ' · pede código de segurança' : ''}`);
    return { ok: true, datas: fm.r.datas, atual: fm.r.atual, livre: fm.r.livre, captcha: img, temCaptcha: fm.r.temCaptcha, ..._nomes(x) };
  } catch (e) {
    P.log(`DARE ${x.nr}: ${e.message || e}`); _prog('', { fim: true });
    _prep = null; P.liberar(true);
    throw e;
  }
}

async function novoCodigo() {
  _exige();
  if (!_prep) throw new Error('O DARE não está mais aberto. Clique em Gerar DARE de novo.');
  await _jsF(JS_CAP_NOVO); await _sleep(1200); _armaRelogio();
  return { ok: true, captcha: await _imgCodigo() };
}

async function emitir({ data, codigo, comExtrato }) {
  _exige();
  const x = _prep;
  if (!x) throw new Error('O DARE não está mais aberto. Clique em Gerar DARE de novo.');
  if (_relogio) { clearTimeout(_relogio); _relogio = null; }
  try {
    const n = _nomes(x);
    _garantePasta(n.dir);
    _prog('Gerando o DARE na SEFIN…');
    _abriu = null;
    const antes = P.win().webContents.getURL();
    const fm = await _jsF(JS_DARE_FORM);
    if (!fm) throw new Error('a tela de emissão do DARE fechou');
    const r = await _noFrame(fm.fr, jsEmitir(data, codigo == null || codigo === '' ? null : codigo));
    if (r && r.erro) throw new Error(r.erro);
    // espera o DARE abrir (mesma janela ou nova) ou o portal recusar o código
    let fim = null;
    const ate = Date.now() + 45000;
    while (Date.now() < ate && !fim) {
      await _sleep(700);
      if (_abriu) { const u = _abriu; _abriu = null; await P.vai(u, 45000); }
      const st = await _jsF(JS_POS_EMITIR);
      if (st && (st.r.doc || st.r.pdf)) fim = st.r;
      else if (st && st.r.erro) {
        P.log(`DARE ${x.nr}: o portal respondeu "${st.r.erro}"`);
        if (st.r.captcha) { _armaRelogio(); _prog('', { fim: true }); return { ok: false, codigoErrado: true, msg: 'O código não conferiu. Digite o novo código.', captcha: await _imgCodigo() }; }
        throw new Error(`o portal respondeu: ${st.r.erro}`);
      }
      if (!fim && P.win().webContents.getURL() !== antes && /impressao|documento/i.test(P.win().webContents.getURL())) { await _sleep(1500); }
    }
    if (!fim) { await _print('dare_emissao.png'); throw new Error('o DARE não apareceu depois de emitir'); }
    const info = fim.doc ? ((await _jsF(JS_DARE_DADOS)) || { r: {} }).r : {};
    await _salvaPdf(n.dare, false);
    const ses = auth.sessao() || {};
    const reg = { data, em: new Date().toISOString(), por: ses.nome || ses.email || '', arquivo: n.dare, total: info.total || '', ateDia: info.ateDia || data, linha: info.linha || '' };
    let arqExt = '', avisoExt = '';
    if (comExtrato) {
      try { arqExt = await _baixarExtrato(x); reg.extrato = arqExt; reg.extratoEm = reg.em; }
      catch (e) { avisoExt = `O DARE foi salvo, mas o extrato não: ${e.message || e}`; P.log(avisoExt); }
    }
    await _marca(x, reg);
    _prog('', { fim: true });
    return { ok: true, arquivo: n.dare, extrato: arqExt, aviso: avisoExt, total: reg.total, ateDia: reg.ateDia };
  } catch (e) {
    P.log(`DARE ${x.nr}: ${e.message || e}`); _prog('', { fim: true });
    throw e;
  } finally {
    if (!_relogio) _fechaPrep();            // código errado mantém a tela aberta (relógio armado); o resto fecha
  }
}
function cancelar() { if (_prep) _fechaPrep(); return { ok: true }; }

module.exports = { init, podeUsar, ler, resumo, dados, previa, preparar, novoCodigo, emitir, cancelar, extrato, PASTA_PADRAO };
