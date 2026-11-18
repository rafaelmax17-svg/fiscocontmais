'use strict';
// Conferência da EFD-Reinf (2.4.6) — pedido do Rafael, 18/11/2026.
//
// Depois que a equipe envia a REINF pelo Domínio, o sistema confere no eCAC o que chegou na Receita, empresa por empresa:
//   1. entra no eCAC com o certificado do escritório (e-CNPJ da Liddera instalado no Windows, escolhido pelo CNPJ):
//      login → "Entrar com gov.br" → "Seu certificado digital". Captcha ou "Autorizar" do gov.br: a PESSOA faz (a janela
//      aparece só nessa hora). O sistema nunca resolve captcha;
//   2. para cada empresa: "Alterar perfil de acesso" → "Procurador de pessoa jurídica - CNPJ" → Alterar. Sem procuração,
//      a empresa fica marcada "sem procuração". Se o eCAC perguntar portal novo ou antigo, fica no antigo;
//   3. EFD-Reinf (reinfweb): série R-4000 (R-4010/R-4020) e série R-2000 (R-2010): lista do período, e para cada evento
//      ainda não lido: Detalhar → "Baixar XML do evento" (valores exatos lidos do XML, python reinf.py);
//   4. fechamentos R-4099 e R-2099: tela "Totalizadores" (recibo, data/hora do processamento e os valores por natureza e
//      código de receita) salva em PDF igual à do eCAC + o XML do recibo/totalizador, na pasta do cliente
//      (Relatórios\AAAA\MM). O quadro "Totais que vão para a DCTFWeb" usa esses valores;
//   5. resultado na nuvem (reinf/<AAAA-MM>_<CNPJ>), visto por toda a equipe na tela Conferência da EFD-Reinf.
// Roda sozinho 1x por dia (12h, num só computador com o certificado do escritório — agenda na nuvem) ou no botão
// "Realizar a conferência". O passo a passo fica em reinf_log.txt, a última tela em reinf_ultima.png e as respostas do
// site em reinf_rede.txt (pasta de dados), para ajustar ao site real.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, BrowserWindow, session } = require('electron');
const auth = require('./auth');
const pastaCliente = require('./pasta_cliente');
const nfePortal = require('./nfe_portal');

const MODULO = 'fiscal-reinf';
const COL = 'reinf';
const URL_LOGIN = 'https://cav.receita.fazenda.gov.br/autenticacao/login';
const URL_ECAC = 'https://cav.receita.fazenda.gov.br/ecac/';
const URL_REINF = 'https://www3.cav.receita.fazenda.gov.br/reinfweb/#/home';
const PARTICAO = 'persist:reinf-ecac';
// e-CNPJ do escritório (procurador). Pode ser trocado pelo Admin em reinf.json (pasta de dados) → { "cnpjCertificado": "..." }
const CNPJ_ESCRITORIO = '36714399000110';

let D = null;                 // { userData(), notificar(c, d), runFiscal(args, out), empresasLocais(), janelaPai() }
let _win = null, _rodando = false, _parar = false, _certFaltou = false, _espera = null, _baixando = false;
let _logTxt = [], _rede = [];
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');
const _fmtCnpj = (c) => _so(c).replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
const _limpo = (o) => JSON.parse(JSON.stringify(o === undefined ? null : o));
const _vivo = () => _win && !_win.isDestroyed();

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
function _prog(txt, extra) { try { D.notificar('reinf:progresso', { txt, ...(extra || {}) }); } catch (_) {} }
async function _print() { try { if (_vivo()) fs.writeFileSync(path.join(D.userData(), 'reinf_ultima.png'), (await _win.webContents.capturePage()).toPNG()); } catch (_) {} }

function init(deps) {
  D = deps;
  app.on('select-client-certificate', (event, webContents, url, lista, callback) => {
    if (!_vivo() || webContents.id !== _win.webContents.id) return;
    const alvo = lista.find((c) => _cnpjCert(c) === cnpjCertificado());
    _log(`o site pediu certificado (${String(url).split('?')[0]}): ${lista.length} no Windows · ${alvo ? 'usando o e-CNPJ do escritório' : 'e-CNPJ do escritório NÃO instalado'}`);
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

// ------------------------------------------------------------------ janela
function _janela() {
  if (_vivo()) return _win;
  const pai = D.janelaPai && D.janelaPai();
  _win = new BrowserWindow({ show: false, width: 1280, height: 880, title: 'FiscoCont+ · eCAC · EFD-Reinf', autoHideMenuBar: true,
    parent: pai && !pai.isDestroyed() ? pai : undefined,
    webPreferences: { partition: PARTICAO, contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
  const ses = session.fromPartition(PARTICAO);
  try { ses.setUserAgent(ses.getUserAgent().replace(/\s(Electron|fiscocont[\w-]*)\/\S+/gi, '')); } catch (_) {}
  _win.webContents.setWindowOpenHandler(({ url }) => { _log(`o site quis abrir janela nova: ${String(url).slice(0, 120)} → mesma janela`); _win.loadURL(url).catch(() => {}); return { action: 'deny' }; });
  _win.webContents.on('did-navigate', (_e, url) => _log(`abriu ${String(url).split('?')[0]}`));
  _win.webContents.on('did-navigate-in-page', (_e, url) => _log(`tela ${String(url).split('?')[0].slice(-80)}`));
  _win.webContents.on('did-fail-load', (_e, cod, desc, url) => { if (cod !== -3) _log(`falha ao abrir ${String(url).split('?')[0]}: ${desc} (${cod})`); });
  _win.webContents.on('dom-ready', () => { _win.webContents.executeJavaScript('window.alert = (m) => console.log("alerta:", m);').catch(() => {}); });
  _win.webContents.on('console-message', (_e, _n, msg) => { if (/^alerta:/.test(msg)) _log(`aviso do site: ${msg.slice(8, 300)}`); });
  _win.on('close', (ev) => { if (_rodando && !_parar) { ev.preventDefault(); _win.hide(); } });
  _win.on('closed', () => { _win = null; });
  if (!ses.__fcReinf) {
    ses.__fcReinf = true;
    ses.on('will-download', (_ev, item) => {
      const dest = path.join(os.tmpdir(), `fc_reinf_${Date.now()}_${item.getFilename().replace(/[^\w.-]+/g, '_')}`);
      item.setSavePath(dest);
      _baixando = true;
      item.once('done', (_e, state) => {
        _baixando = false;
        _log(`download ${state}: ${item.getFilename()}`);
        if (_espera) { const w = _espera; _espera = null; w({ state, dest, nome: item.getFilename() }); }
      });
    });
    // respostas do site (para ajustar ao site real): endereço e tipo; nada de conteúdo pessoal no arquivo
    ses.webRequest.onCompleted((det) => {
      if (!/reinfweb|cav\.receita/.test(det.url) || !/xhr|fetch/i.test(det.resourceType || '')) return;
      _rede.push(`${new Date().toLocaleTimeString('pt-BR')} ${det.method} ${det.statusCode} ${String(det.url).split('?')[0].slice(0, 160)}`);
      try { fs.writeFileSync(path.join(D.userData(), 'reinf_rede.txt'), _rede.slice(-600).join('\n')); } catch (_) {}
    });
  }
  return _win;
}
const _js = (code) => (_vivo() ? _win.webContents.executeJavaScript(code, true) : Promise.reject(new Error('a janela do eCAC foi fechada.')));
async function _vai(url, ms = 45000) {
  if (!_vivo()) throw new Error('a janela do eCAC foi fechada.');
  await _win.loadURL(url).catch((e) => _log(`ao abrir ${url}: ${e.message || e}`));
  await _pronto(ms);
}
async function _pronto(ms = 30000) {
  const fim = Date.now() + ms;
  await _sleep(500);
  while (Date.now() < fim) {
    if (!_vivo()) throw new Error('a janela do eCAC foi fechada.');
    if (!_win.webContents.isLoading()) { try { if (await _js('document.readyState') === 'complete') { await _sleep(700); return; } } catch (_) {} }
    await _sleep(300);
  }
}
const _url = () => (_vivo() ? _win.webContents.getURL() : '');
function _mostra(sim) {
  if (!_vivo()) return;
  if (!sim) { _win.hide(); return; }
  const pai = D.janelaPai && D.janelaPai();
  if (pai && !pai.isDestroyed()) { const b = pai.getBounds(), [w, h] = _win.getSize(); _win.setPosition(Math.round(b.x + (b.width - w) / 2), Math.round(b.y + (b.height - h) / 2)); }
  _win.show(); _win.focus();
}
function _esperaDownload(ms = 60000) {
  return new Promise((resolve) => {
    const t = setTimeout(() => { if (_espera) { _espera = null; resolve({ state: 'tempo' }); } }, ms);
    _espera = (r) => { clearTimeout(t); resolve(r); };
  });
}

// ------------------------------------------------------------------ JS das páginas (por texto, sem depender de ids)
const JS_BASE = `
  const vis = (e) => { if (!e || !e.getClientRects || !e.getClientRects().length) return false; const cs = getComputedStyle(e); const b = e.getBoundingClientRect(); return cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05 && b.width > 0 && b.height > 0; };
  const norm = (s) => String(s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/\\s+/g, ' ').trim().toUpperCase();
  const txt = (e) => norm(e && (e.value || e.innerText || e.textContent || e.alt || e.title || (e.getAttribute && e.getAttribute('aria-label'))));
  const clicaveis = () => [...document.querySelectorAll('a, button, input[type=button], input[type=submit], input[type=image], [role=button], [role=tab], [role=menuitem], li, span, div.card, mat-card')].filter(vis);
  const setVal = (inp, v) => { inp.focus(); const d = Object.getOwnPropertyDescriptor(inp.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value');
    d.set.call(inp, ''); inp.dispatchEvent(new Event('input', { bubbles: true }));
    d.set.call(inp, v); inp.dispatchEvent(new InputEvent('input', { bubbles: true, data: v, inputType: 'insertText' }));
    inp.dispatchEvent(new Event('change', { bubbles: true })); inp.dispatchEvent(new Event('blur', { bubbles: true })); };
`;
// clica no elemento visível (o menor) cujo texto bate com a expressão
const JS_CLICA = (re, nao) => `(() => { ${JS_BASE}
  const re = ${re}; const nao = ${nao || 'null'};
  const l = clicaveis().filter((x) => re.test(txt(x)) && !(nao && nao.test(txt(x)))).sort((a, b) => txt(a).length - txt(b).length);
  if (!l.length) return false;
  const alvo = l[0].closest('a, button, [role=button], [role=tab], [role=menuitem], li') || l[0];
  alvo.scrollIntoView({ block: 'center' }); alvo.click(); return txt(alvo).slice(0, 80);
})()`;
const JS_TEXTO = `(() => document.body ? document.body.innerText.slice(0, 20000) : '')()`;
// Captcha que a PESSOA vê de verdade. Achado real (18/11): a página de login do eCAC carrega o hCaptcha invisível — o
// sistema achou que era para a pessoa e mostrou a página do eCAC. Agora só conta a caixa "Sou humano" ou o desafio de
// imagens quando estão visíveis na tela (nada escondido, transparente ou fora da tela).
const JS_CAPTCHA = `(() => {
  const r = document.querySelector('[name="h-captcha-response"], [name="g-recaptcha-response"]');
  const vista = (f) => { const b = f.getBoundingClientRect(); if (b.width < 60 || b.height < 60 || b.bottom <= 0 || b.top >= innerHeight || b.right <= 0 || b.left >= innerWidth) return false;
    for (let el = f; el && el !== document.documentElement; el = el.parentElement) { const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.1) return false; } return true; };
  const fr = [...document.querySelectorAll('iframe[src*="hcaptcha"], iframe[src*="recaptcha"]')].filter(vista);
  const desafio = fr.some((f) => /challenge|desafio/i.test(f.title || '') || f.getBoundingClientRect().height > 200);
  const caixa = fr.some((f) => /checkbox|caixa/i.test(f.title || '') || f.getBoundingClientRect().height <= 110);
  return { tem: desafio || caixa, desafio, caixa, ok: !!(r && r.value) };
})()`;
// Na janela fica só o quadro do captcha (e o desafio de imagens), com a faixa do FiscoCont+ — nada da página do eCAC.
const JS_SO_CAPTCHA = `(() => {
  if (!document.getElementById('fcFaixa')) {
    const st = document.createElement('style'); st.id = 'fcEstilo';
    st.textContent = 'html,body{overflow:hidden!important;background:#f3f5fa!important}body *{visibility:hidden!important}'
      + 'iframe[src*="hcaptcha"],iframe[src*="recaptcha"],#fcFaixa,#fcFaixa *{visibility:visible!important}'
      + '.fc-alvo{position:fixed!important;top:150px!important;left:50%!important;transform:translateX(-50%)!important;margin:0!important;z-index:2147483000!important}'
      + '#fcFaixa{position:fixed;top:0;left:0;right:0;z-index:2147483001;background:linear-gradient(135deg,#2563eb,#0891b2);color:#fff;padding:16px 18px;font:14px/1.4 "Segoe UI",system-ui,sans-serif}'
      + '#fcFaixa b{display:block;font-size:15px}#fcFaixa span{display:block;opacity:.92;font-size:12.5px;margin-top:4px}';
    document.head.appendChild(st);
    const f = document.createElement('div'); f.id = 'fcFaixa';
    f.innerHTML = '<b>Conferência da EFD-Reinf</b><span>Marque “Sou humano”. Depois disso o sistema continua sozinho e fecha esta janela.</span>';
    document.body.appendChild(f);
  }
  const cx = [...document.querySelectorAll('iframe[src*="hcaptcha"], iframe[src*="recaptcha"]')].find((f) => f.getBoundingClientRect().height <= 110 && f.getBoundingClientRect().height > 40);
  if (cx) (cx.closest('.h-captcha, .g-recaptcha') || cx.parentElement).classList.add('fc-alvo');
  return true;
})()`;
const JS_TIRA_FAIXA = `(() => { ['fcEstilo', 'fcFaixa'].forEach((i) => { const e = document.getElementById(i); if (e) e.remove(); }); document.querySelectorAll('.fc-alvo').forEach((e) => e.classList.remove('fc-alvo')); })()`;
// "Entrar com gov.br": o botão é texto + imagem do gov.br (achado real 18/11: o sistema clicava no título "ACESSO GOVBR")
const JS_GOVBR = (modo) => `(() => { ${JS_BASE}
  // qualquer elemento (a, button, input, div, img…) do botão: link para o gov.br, texto "Entrar com" ou imagem do gov.br
  const docs = [document, ...[...document.querySelectorAll('iframe')].map((f) => { try { return f.contentDocument; } catch (_) { return null; } }).filter(Boolean)];
  const todos = docs.flatMap((d) => [...d.querySelectorAll('a, button, input, [onclick], [role=button], img, div, span')]).filter(vis);
  // achado real (18/11): o botão é <input type="image" src=".../gov-br.png" alt="Acesso Gov BR" onclick="validarHcaptcha('govBr')">
  const ehLink = (x) => /govbrsso|sso\\.acesso\\.gov\\.br|validarHcaptcha\\(\\s*'govBr'/i.test((x.getAttribute('href') || '') + ' ' + (x.getAttribute('onclick') || '') + ' ' + (x.getAttribute('formaction') || ''));
  const ehImg = (x) => (x.tagName === 'IMG' || (x.tagName === 'INPUT' && x.type === 'image')) && /GOV[\\s._-]?BR/i.test((x.alt || '') + ' ' + (x.getAttribute('src') || '')) && !/SAIBA/.test(txt(x.parentElement));
  const ehTexto = (x) => /^ENTRAR COM/.test(txt(x)) || ehImg(x);
  let alvo = todos.find(ehLink) || todos.filter(ehTexto).sort((a, b) => txt(a).length - txt(b).length)[0];
  if (!alvo) return false;
  alvo = alvo.closest('a, button, [onclick], [role=button], input') || alvo;
  const r = alvo.getBoundingClientRect();
  if ('${modo || 'clica'}' === 'rect') return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), tag: alvo.tagName };
  alvo.scrollIntoView({ block: 'center' }); alvo.click(); return (txt(alvo) || alvo.tagName).slice(0, 60);
})()`;
// para o passo a passo: o que a página tem de gov.br / entrar (para ajustar ao site real)
const JS_DIAG = `(() => { const out = [];
  document.querySelectorAll('a, button, input, form, iframe, img, [onclick]').forEach((x) => { const h = x.outerHTML; if (/gov\\.?br|entrar|sso|captcha/i.test(h) && out.length < 18) out.push(h.replace(/\\s+/g, ' ').slice(0, 220)); });
  return out.join(' || '); })()`;
// "Alterar perfil de acesso" › Procurador de pessoa jurídica - CNPJ
const JS_PERFIL = (cnpj, modo) => `(() => { ${JS_BASE}
  // o rótulo mais interno (o próprio texto, não a caixa que também o contém — senão pegava o campo do CPF de cima)
  const reP = /PROCURADOR DE PESSOA JURIDICA/;
  const rot = [...document.querySelectorAll('label, span, div, td, p, h4, h5, legend, strong, b')].filter(vis).filter((x) => reP.test(txt(x)) && txt(x).length < 80)
    .filter((x) => ![...x.children].some((c) => reP.test(txt(c))))[0];
  if (!rot) return { ok: false, motivo: 'campo "Procurador de pessoa jurídica - CNPJ" não encontrado' };
  let box = rot, inp = null, bt = null;
  for (let i = 0; i < 5 && box && !(inp && bt); i++) {
    box = box.parentElement;
    inp = inp || [...box.querySelectorAll('input[type=text], input[type=tel], input:not([type])')].filter(vis)[0];
    bt = [...box.querySelectorAll('input[type=button], input[type=submit], button, a')].filter(vis).find((b) => /^ALTERAR$/.test(txt(b)));
  }
  if (!inp) { const todos = [...document.querySelectorAll('input[type=text], input[type=tel], input:not([type])')].filter(vis); inp = todos.find((x) => rot.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING); }
  if (!inp) return { ok: false, motivo: 'campo do CNPJ não encontrado' };
  if (!bt) { const bs = [...document.querySelectorAll('input[type=button], input[type=submit], button')].filter(vis).filter((b) => /^ALTERAR$/.test(txt(b)));
    bt = bs.find((b) => inp.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) || bs[0]; }
  if (!bt) return { ok: false, motivo: 'botão Alterar não encontrado' };
  const m = '${modo || 'valor'}';
  if (m === 'foca') { inp.scrollIntoView({ block: 'center' }); inp.focus(); inp.select && inp.select(); inp.value = ''; inp.dispatchEvent(new Event('input', { bubbles: true })); return { ok: true, max: inp.maxLength, mascara: inp.getAttribute('onkeypress') || inp.getAttribute('data-mask') || '' }; }
  if (m === 'valor') setVal(inp, '${cnpj}');
  if (m === 'clica' || m === 'valor') { bt.click(); return { ok: true, campo: inp.value }; }
  return { ok: true, campo: inp.value };
})()`;
// mensagem que o eCAC mostrou depois do Alterar (o parágrafo inteiro, com o motivo)
const JS_MSG_PERFIL = `(() => { ${JS_BASE}
  const els = [...document.querySelectorAll('div, p, span, td, li')].filter(vis).filter((x) => /NAO FOI POSSIVEL|PROCURAC|NAO (EXISTE|HA|POSSUI)|INVALID|ATENCAO/.test(txt(x)) && txt(x).length < 600)
    .sort((a, b) => txt(a).length - txt(b).length);
  const alvo = els.find((x) => txt(x).length > 40) || els[0];
  return alvo ? (alvo.closest('div') || alvo).innerText.replace(/\\s+/g, ' ').trim().slice(0, 400) : '';
})()`;
// "Alterar perfil de acesso" escondido (menu do usuário fechado no portal novo): abre o menu ou clica direto
const JS_ABRE_PERFIL = `(() => { ${JS_BASE}
  const todos = [...document.querySelectorAll('a, button, input[type=button], li, span')].filter((x) => /ALTERAR PERFIL/.test(txt(x)) && txt(x).length < 60);
  if (todos.length) { const a = todos.sort((x, y) => txt(x).length - txt(y).length)[0]; (a.closest('a, button, li') || a).click(); return txt(a).slice(0, 60); }
  const menu = [...document.querySelectorAll('a, button, [role=button]')].filter(vis).find((x) => /^PERFIL$|MEU PERFIL|PERFIL DE ACESSO|OPCOES DO USUARIO/.test(txt(x)));
  if (menu) { menu.click(); return 'menu:' + txt(menu).slice(0, 40); }
  return false;
})()`;
// período de apuração (dois campos MM/AAAA) e Listar
const JS_PERIODO = (mmaaaa) => `(() => { ${JS_BASE}
  const inps = [...document.querySelectorAll('input')].filter(vis).filter((i) => !['checkbox', 'radio', 'button', 'submit', 'hidden'].includes(i.type));
  const per = inps.filter((i) => /MM\\/?AAAA|PERIODO|APURACAO|COMPETENCIA/.test(norm(i.placeholder + ' ' + i.name + ' ' + i.id + ' ' + (i.getAttribute('formcontrolname') || '') + ' ' + (i.closest('div, td') ? i.closest('div, td').innerText : ''))));
  const alvo = (per.length ? per : inps).slice(0, 2);
  alvo.forEach((i) => setVal(i, '${mmaaaa}'));
  return alvo.length;
})()`;
// tabela da lista: cabeçalho → colunas (Período, Estabelecimento, Beneficiário, Número do recibo, Tipo de evento, Recepção)
const JS_LISTA = `(() => { ${JS_BASE}
  const t = [...document.querySelectorAll('table')].filter(vis).find((x) => /RECIBO/.test(txt(x.querySelector('thead') || x.rows[0])));
  if (!t) return { tem: false, vazio: /NENHUM (REGISTRO|EVENTO)|NAO (FORAM )?ENCONTRAD|SEM REGISTRO/.test(norm(document.body.innerText)) };
  const cab = [...(t.querySelector('thead') ? t.querySelector('thead').rows[0].cells : t.rows[0].cells)].map((c) => txt(c));
  const idx = (re) => cab.findIndex((c) => re.test(c));
  const ix = { per: idx(/PERIODO/), est: idx(/ESTABELEC/), ben: idx(/BENEFICIARIO|PRESTADOR|CNPJ DO PRESTADOR/), rec: idx(/RECIBO/), tipo: idx(/TIPO/), dt: idx(/RECEPCAO|DATA/), sit: idx(/SITUACAO|STATUS/) };
  const corpo = t.tBodies[0] ? [...t.tBodies[0].rows] : [...t.rows].slice(1);
  const rows = corpo.map((r, i) => { const c = [...r.cells].map((x) => (x.innerText || '').trim());
    return { i, per: c[ix.per] || '', est: c[ix.est] || '', benef: c[ix.ben] || '', recibo: c[ix.rec] || '', tipo: c[ix.tipo] || '', recepcao: c[ix.dt] || '', sit: c[ix.sit] || '',
      det: !![...r.querySelectorAll('button, a, input')].find((b) => /DETALHAR|VISUALIZAR/.test(txt(b))), tot: !![...r.querySelectorAll('button, a, input')].find((b) => /TOTALIZADOR/.test(txt(b))) }; })
    .filter((r) => r.recibo || r.per);
  const prox = [...document.querySelectorAll('a, button, li')].filter(vis).find((x) => /^PROXIMA|^›|^»/.test(txt(x)) && !x.classList.contains('disabled') && !(x.parentElement && x.parentElement.classList.contains('disabled')));
  return { tem: true, cab, rows, prox: !!prox };
})()`;
// botão da linha: pelo número do recibo (ou pela posição, quando não há recibo)
const JS_LINHA_BT = (i, re, recibo) => `(() => { ${JS_BASE}
  const t = [...document.querySelectorAll('table')].filter(vis).find((x) => /RECIBO/.test(txt(x.querySelector('thead') || x.rows[0])));
  if (!t) return false;
  const corpo = t.tBodies[0] ? [...t.tBodies[0].rows] : [...t.rows].slice(1);
  const rec = ${JSON.stringify(recibo || '')};
  const r = rec ? corpo.find((x) => (x.innerText || '').includes(rec)) : corpo[${i}]; if (!r) return false;
  const b = [...r.querySelectorAll('button, a, input')].find((x) => ${re}.test(txt(x)));
  if (!b) return false; b.scrollIntoView({ block: 'center' }); b.click(); return true;
})()`;
// tela "Totalizadores": campos (rótulo → valor) e as tabelas
const JS_TOTALIZADOR = `(() => { ${JS_BASE}
  const kv = {};
  [...document.querySelectorAll('label, dt, span, div, td, th, p')].filter(vis).forEach((el) => {
    const t = txt(el); if (!t || t.length > 60 || el.children.length > 2) return;
    if (/^(NUMERO DO RECIBO DO EVENTO|DATA\\/HORA DO PROCESSAMENTO|PERIODO DE APURACAO|IDENTIFICACAO DA ESCRITURACAO)$/.test(t)) {
      let v = el.nextElementSibling ? el.nextElementSibling.innerText : ''; if (!v && el.parentElement) v = el.parentElement.innerText.replace(el.innerText, '');
      kv[t] = String(v || '').trim().split('\\n')[0];
    }
  });
  const tabelas = [...document.querySelectorAll('table')].filter(vis).map((t) => {
    const cab = [...(t.querySelector('thead') ? t.querySelector('thead').rows[0].cells : t.rows[0].cells)].map((c) => txt(c));
    const corpo = t.tBodies[0] ? [...t.tBodies[0].rows] : [...t.rows].slice(1);
    return { cab, rows: corpo.map((r) => [...r.cells].map((c) => (c.innerText || '').trim())) };
  }).filter((t) => t.cab.some((c) => /CODIGO DE RECEITA/.test(c)));
  return { ok: tabelas.length > 0 || !!kv['NUMERO DO RECIBO DO EVENTO'], kv, tabelas, sem: /SEM MOVIMENTO/.test(norm(document.body.innerText)) };
})()`;

// ------------------------------------------------------------------ passos
async function _humano(rotulo) {
  // captcha ou autorização do gov.br: quem faz é a pessoa. A janela só aparece se continuar parado nisso por alguns
  // segundos, e mostra só o quadro do captcha (nada da página do eCAC) — para não confundir a equipe.
  const precisa = async () => {
    const c = await _js(JS_CAPTCHA).catch(() => ({}));
    const consent = /sso\.acesso\.gov\.br/.test(_url()) && /\bAUTORIZAR\b/.test((await _js(JS_TEXTO).catch(() => '')).normalize('NFD').toUpperCase());
    return { cap: !!(c.tem && !c.ok), consent };
  };
  let p = await precisa();
  if (!p.cap && !p.consent) return false;
  const u0 = _url();
  await _sleep(5000);
  if (_url() !== u0) return true;                       // seguiu sozinho
  p = await precisa();
  if (!p.cap && !p.consent) return true;
  _log(`${rotulo}: esperando a pessoa (${p.consent ? 'autorização do gov.br' : 'captcha'})`);
  _prog(p.consent ? 'O gov.br pediu autorização: confira e autorize na janela que abriu.' : 'Marque o "Sou humano" na janela que abriu.', { humano: true });
  if (p.cap && !p.consent) { await _js(JS_SO_CAPTCHA).catch(() => {}); _win.setSize(500, 660); }
  _mostra(true);
  const fim = Date.now() + 5 * 60000;
  while (Date.now() < fim && _vivo() && !_parar) {
    await _sleep(1000);
    if (_url() !== u0) break;
    const c2 = await _js(JS_CAPTCHA).catch(() => ({}));
    if (!p.consent && (c2.ok || !c2.tem)) { await _sleep(1200); break; }
  }
  _mostra(false);
  await _js(JS_TIRA_FAIXA).catch(() => {});
  try { _win.setSize(1280, 880); } catch (_) {}
  return true;
}

async function _login() {
  _prog('Entrando no eCAC com o certificado do escritório…');
  await _vai(URL_ECAC);
  if (/cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url()) && !/autenticacao/.test(_url())) { _log('sessão do eCAC ainda aberta'); return; }
  if (!/autenticacao\/login/.test(_url())) await _vai(URL_LOGIN);
  for (let tent = 0; tent < 4 && !/sso\.acesso\.gov\.br/.test(_url()); tent++) {
    await _sleep(1500);                                         // a página monta o botão depois de carregar
    let t = false;
    if (tent < 2) t = await _js(JS_GOVBR('clica')).catch(() => false);
    else if (tent === 2) {                                      // clique "de verdade" (mouse) no botão
      const r = await _js(JS_GOVBR('rect')).catch(() => false);
      if (r && r.x) { for (const type of ['mouseMove', 'mouseDown', 'mouseUp']) _win.webContents.sendInputEvent({ type, x: r.x, y: r.y, button: 'left', clickCount: 1 }); t = `mouse em ${r.tag}`; }
    } else {                                                    // a função que o próprio botão chama (hCaptcha invisível + envio)
      t = await _js(`(() => { if (typeof validarHcaptcha === 'function') { validarHcaptcha('govBr'); return 'validarHcaptcha'; } const f = document.getElementById('frmLoginCert'); if (f) { f.submit(); return 'formulário'; } return false; })()`).catch(() => false);
    }
    _log(`login: ${t ? `clicou em "${t}"` : 'botão gov.br não encontrado'}`);
    if (!t && tent === 0) _log(`login · página: ${await _js(JS_DIAG).catch(() => '')}`);
    for (let i = 0; i < 16 && !/sso\.acesso\.gov\.br/.test(_url()); i++) await _sleep(500);
    await _pronto();
    if (!/sso\.acesso\.gov\.br/.test(_url())) await _humano('login do eCAC');   // captcha do botão, se aparecer de verdade
  }
  if (!/sso\.acesso\.gov\.br|cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url())) _log(`login: continuou em ${_url().split('?')[0]}`);
  if (/sso\.acesso\.gov\.br/.test(_url())) {
    await _humano('gov.br (antes do certificado)');
    const c = await _js(JS_CLICA('/SEU CERTIFICADO DIGITAL$|CERTIFICADO DIGITAL$/', '/NUVEM/')).catch(() => false);
    _log(`gov.br: ${c ? 'Seu certificado digital' : 'opção do certificado não encontrada'}`);
    await _pronto(45000);
  }
  for (let i = 0; i < 40; i++) {
    if (_certFaltou) throw new Error(`o certificado do escritório (e-CNPJ ${_fmtCnpj(cnpjCertificado())}) não está instalado no Windows deste computador.`);
    const u = _url();
    if (/cav\.receita\.fazenda\.gov\.br\/ecac/i.test(u)) { _log('eCAC aberto'); return; }
    if (await _humano('gov.br')) continue;
    await _sleep(1500);
  }
  await _print();
  throw new Error('não consegui entrar no eCAC (veja o "Passo a passo").');
}

async function _portalAntigo() {
  const t = (await _js(JS_TEXTO).catch(() => '')).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  if (/NOVO/.test(t) && /ANTIG/.test(t) && /(PORTAL|VERSAO|ECAC)/.test(t)) {
    const c = await _js(JS_CLICA('/ANTIG|VERSAO (ANTERIOR|CLASSICA)|CONTINUAR (NO|NA) (ATUAL|VERSAO ATUAL)/')).catch(() => false);
    if (c) { _log(`portal antigo: "${c}"`); await _pronto(); }
  }
}

// troca o perfil para a empresa. Devolve { ok } ou { semProcuracao } ou { erro }
async function _perfil(emp) {
  const norm = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  for (let tent = 0; tent < 3; tent++) {
    await _vai(URL_ECAC);
    // achado real (18/11): depois de um "não foi possível alterar o perfil", as empresas seguintes não achavam o botão —
    // a sessão do eCAC cai ou fica um aviso aberto. Agora entra de novo se precisar e fecha o aviso antes.
    if (/autenticacao|sso\.acesso/.test(_url())) { _log('a sessão do eCAC caiu: entrando de novo'); await _login(); await _vai(URL_ECAC); }
    await _portalAntigo();
    await _js(JS_CLICA('/^(OK|FECHAR|X)$/')).catch(() => false);
    let ab = await _js(JS_CLICA('/ALTERAR PERFIL/')).catch(() => false);
    if (!ab) { ab = await _js(JS_ABRE_PERFIL).catch(() => false); if (ab && /^menu:/.test(ab)) { await _sleep(1000); ab = await _js(JS_ABRE_PERFIL).catch(() => false); } }
    if (!ab) {
      _log(`${emp.nome}: "Alterar perfil de acesso" não encontrado (tela: ${(await _js(JS_TEXTO).catch(() => '')).replace(/\s+/g, ' ').slice(0, 300)})`);
      if (tent < 2) { await _sleep(2000); continue; }
      await _print(); return { erro: '"Alterar perfil de acesso" não encontrado no eCAC.' };
    }
    await _sleep(1800);
    // digita o CNPJ de verdade (a máscara do campo formata), em vez de só preencher o valor
    const f = await _js(JS_PERFIL(_so(emp.cnpj), 'foca')).catch((e) => ({ ok: false, motivo: e.message }));
    if (!f.ok) { await _print(); return { erro: f.motivo }; }
    _win.webContents.insertText(tent === 1 ? _fmtCnpj(emp.cnpj) : _so(emp.cnpj));
    await _sleep(500);
    const c = await _js(JS_PERFIL(_so(emp.cnpj), 'clica')).catch((e) => ({ ok: false, motivo: e.message }));
    _log(`${emp.nome}: perfil · campo ficou "${c.campo || ''}" (tentativa ${tent + 1})`);
    await _sleep(2500); await _pronto();
    const t = norm(await _js(JS_TEXTO).catch(() => ''));
    const msg = norm(await _js(JS_MSG_PERFIL).catch(() => ''));
    if (t.includes(_fmtCnpj(emp.cnpj)) || (t.includes(_so(emp.cnpj)) && !/NAO FOI POSSIVEL/.test(msg))) { await _portalAntigo(); _log(`${emp.nome}: perfil de procurador ok`); return { ok: true }; }
    _log(`${emp.nome}: o eCAC respondeu "${msg || '(sem mensagem)'}"`);
    if (/PROCURAC/.test(msg) && /(NAO|INEXIST|SEM|EXPIRAD|VENCID|CANCELAD)/.test(msg)) return { semProcuracao: true, msg };
    if (tent < 2 && /NAO FOI POSSIVEL/.test(msg)) {
      // achado real (18/11): depois de uma empresa, a troca para a próxima dava "não foi possível alterar o perfil" (a
      // seguinte funcionava). Começa uma sessão nova (perfil do titular) e tenta de novo.
      await _print();
      _log(`${emp.nome}: saindo do eCAC e entrando de novo para trocar o perfil`);
      await _novaSessao();
      continue;
    }
    await _print();
    return { erro: msg ? `o eCAC respondeu: ${msg.toLowerCase()}` : 'não consegui confirmar a troca de perfil no eCAC.' };
  }
  return { erro: 'não consegui trocar o perfil no eCAC.' };
}

async function _novaSessao() {
  try {
    const ses = session.fromPartition(PARTICAO);
    await ses.clearStorageData({ origins: ['https://cav.receita.fazenda.gov.br', 'https://www3.cav.receita.fazenda.gov.br'] });
    await ses.clearStorageData({ storages: ['cookies'] }).catch(() => {});
  } catch (e) { _log(`limpar a sessão: ${e.message || e}`); }
  await _login();
}

async function _abreReinf() {
  await _vai(URL_REINF, 60000);
  for (let i = 0; i < 20 && !/reinfweb/.test(_url()); i++) await _sleep(500);
  await _sleep(2500);
  await _js(JS_CLICA('/^(FECHAR|OK|CIENTE|ENTENDI|CONTINUAR)$/')).catch(() => false);
}

// lista de uma série no período: abre a aba e o item de lista, preenche o período e lista (todas as páginas)
async function _lista(serie, comp) {
  const mmaaaa = `${comp.slice(5, 7)}/${comp.slice(0, 4)}`;
  const aba = serie === '4000' ? '/RENDIMENTOS PAGOS/' : '/RETENCOES PREVIDENCIARIAS/';
  const item = serie === '4000' ? ['/PAGAMENTO.?CREDITO.*(LISTA|CONSULT)|LISTAR EVENTOS ENVIADOS/', '/PAGAMENTO.?CREDITO/', '/BENEFICIARIO PESSOA JURIDICA/']
    : ['/SERVICOS TOMADOS/', '/R-?2010/'];
  await _js(JS_CLICA(aba)).catch(() => false); await _sleep(1500);
  let foi = false;
  for (const re of item) { const c = await _js(JS_CLICA(re, '/FECHAMENTO|REABERTURA|TOTALIZADOR/')).catch(() => false); if (c) { _log(`R-${serie}: "${c}"`); foi = true; break; } }
  if (!foi) { await _print(); return { erro: `não achei a lista de eventos da série R-${serie}.` }; }
  await _sleep(2000);
  const n = await _js(JS_PERIODO(mmaaaa)).catch(() => 0);
  if (!n) { await _print(); return { erro: 'não achei o campo do período de apuração.' }; }
  await _js(JS_CLICA('/^(LISTAR|CONSULTAR|PESQUISAR)$/')).catch(() => false);
  const todas = [];
  for (let pag = 0; pag < 20; pag++) {
    let l = null;
    for (let i = 0; i < 20; i++) { await _sleep(700); l = await _js(JS_LISTA).catch(() => null); if (l && (l.tem || l.vazio)) break; }
    if (!l || !l.tem) { if (l && l.vazio) return { rows: todas }; await _print(); return pag ? { rows: todas } : { rows: [], aviso: 'a lista não apareceu.' }; }
    if (pag === 0) _log(`R-${serie} colunas: ${l.cab.join(' | ')}`);
    todas.push(...l.rows.map((r) => ({ ...r, pag })));
    if (!l.prox || l.rows.length < 10) break;
    await _js(JS_CLICA('/^PROXIMA|^›$|^»$/')).catch(() => false);
  }
  return { rows: todas, mmaaaa };
}

// Detalhar → Baixar XML do evento → Voltar
async function _xmlEvento(row, serie, comp) {
  // a lista precisa estar na tela (o Voltar às vezes volta sem ela): lista de novo e procura a linha pelo recibo
  if (!(await _js(JS_LISTA).catch(() => ({}))).tem) { const l2 = await _lista(serie, comp); if (l2.erro) return null; }
  let ok = false;
  for (let pag = 0; pag < 20 && !ok; pag++) {
    ok = await _js(JS_LINHA_BT(row.i, '/DETALHAR|VISUALIZAR/', row.recibo)).catch(() => false);
    if (!ok) { const l = await _js(JS_LISTA).catch(() => ({})); if (!l.prox) break; await _js(JS_CLICA('/^PROXIMA|^›$|^»$/')).catch(() => false); await _sleep(1500); }
  }
  if (!ok) return null;
  await _sleep(2000);
  const baixa = _esperaDownload(45000);
  const c = await _js(JS_CLICA('/BAIXAR XML DO EVENTO/')).catch(() => false);
  let r = { state: 'sem_botao' };
  if (c) r = await baixa; else if (_espera) _espera = null;
  await _js(JS_CLICA('/^VOLTAR$/')).catch(() => false);
  await _sleep(1800);
  return r.state === 'completed' ? r.dest : null;
}

async function _lerXmls(arqs) {
  if (!arqs.length) return [];
  const out = path.join(os.tmpdir(), `fc_reinf_x_${Date.now()}.json`);
  const args = ['reinf-xml', '--json', out];
  arqs.forEach((a) => args.push('--xml', a));
  await D.runFiscal(args, out);
  const r = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
  return (r.eventos || []);
}

// fechamento (R-4099 / R-2099) → Totalizadores: PDF igual à tela do eCAC + XML do recibo/totalizador
async function _fechamento(serie, comp, emp, pasta) {
  const mmaaaa = `${comp.slice(5, 7)}/${comp.slice(0, 4)}`;
  const aba = serie === '4000' ? '/RENDIMENTOS PAGOS/' : '/RETENCOES PREVIDENCIARIAS/';
  const ev = serie === '4000' ? '4099' : '2099';
  await _js(JS_CLICA(aba)).catch(() => false); await _sleep(1500);
  const c = await _js(JS_CLICA(`/FECHAMENTO.*(R-?${ev})|R-?${ev}/`)).catch(() => false) || await _js(JS_CLICA('/FECHAMENTO E REABERTURA|FECHAMENTO\\/REABERTURA/')).catch(() => false);
  if (!c) return { fechado: false, aviso: `não achei o fechamento R-${ev}.` };
  _log(`R-${ev}: "${c}"`);
  await _sleep(2000);
  await _js(JS_PERIODO(mmaaaa)).catch(() => 0);
  await _js(JS_CLICA('/^(LISTAR|CONSULTAR|PESQUISAR)$/')).catch(() => false);
  let l = null;
  for (let i = 0; i < 20; i++) { await _sleep(700); l = await _js(JS_LISTA).catch(() => null); if (l && (l.tem || l.vazio)) break; }
  const rows = (l && l.rows) || [];
  _log(`R-${ev}: ${rows.length} linha(s) ${rows.map((r) => `${r.tipo || r.sit} ${r.recibo}`).join(' · ')}`);
  // o último evento do período: fechamento (com totalizador) ou reabertura
  const ult = rows.filter((r) => r.recibo).slice(-1)[0];
  if (!ult) return { fechado: false };
  if (/REABERT/i.test(`${ult.tipo} ${ult.sit}`)) return { fechado: false, reaberto: true, recibo: ult.recibo, recepcao: ult.recepcao };
  const linha = rows.findIndex((r) => r === ult);
  const okTot = await _js(JS_LINHA_BT(linha, '/TOTALIZADOR/', ult.recibo)).catch(() => false) || await _js(JS_LINHA_BT(linha, '/DETALHAR|VISUALIZAR/', ult.recibo)).catch(() => false);
  const res = { fechado: true, recibo: ult.recibo, recepcao: ult.recepcao, porCodigo: [], porNatureza: [] };
  if (!okTot) return res;
  await _sleep(2500);
  if (!(await _js(JS_TOTALIZADOR).catch(() => ({}))).ok) { await _js(JS_CLICA('/TOTALIZADOR/')).catch(() => false); await _sleep(2500); }
  const t = await _js(JS_TOTALIZADOR).catch(() => ({ ok: false }));
  if (!t.ok) { await _print(); return { ...res, aviso: 'a tela de totalizadores não abriu.' }; }
  res.recibo = t.kv['NUMERO DO RECIBO DO EVENTO'] || res.recibo;
  res.dhProcess = t.kv['DATA/HORA DO PROCESSAMENTO'] || '';
  res.semMovimento = !!t.sem;
  const num = (v) => { const n = parseFloat(String(v || '').replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.')); return Number.isFinite(n) ? n : 0; };
  for (const tb of t.tabelas) {
    const ix = (re) => tb.cab.findIndex((x) => re.test(x));
    const iNat = ix(/NATUREZA/), iCod = ix(/CODIGO DE RECEITA/), iEnv = ix(/ENVIADO|DCTF/), iRet = ix(/^VALOR RETIDO$/), iSus = ix(/SUSPENS/), iDx = ix(/DEIXOU/);
    const linhas = tb.rows.map((r) => ({ nat: iNat >= 0 ? r[iNat] : '', cod: _so(r[iCod]), retido: num(r[iRet >= 0 ? iRet : iEnv]), enviado: num(r[iEnv >= 0 ? iEnv : iRet]), suspenso: iSus >= 0 ? num(r[iSus]) : 0, deixou: iDx >= 0 ? num(r[iDx]) : 0 })).filter((x) => x.cod);
    if (iNat >= 0) res.porNatureza.push(...linhas); else res.porCodigo.push(...linhas);
  }
  if (!res.porCodigo.length && res.porNatureza.length) {          // sem a segunda tabela: soma por código
    const m = {}; res.porNatureza.forEach((x) => { m[x.cod] = m[x.cod] || { cod: x.cod, enviado: 0, deixou: 0 }; m[x.cod].enviado += x.enviado; m[x.cod].deixou += x.deixou; });
    res.porCodigo = Object.values(m);
  }
  // PDF da própria tela + XML do totalizador, na pasta do cliente
  const nome = `REINF Totalizador R-${ev} ${comp.slice(5, 7)}${comp.slice(0, 4)}`;
  try {
    const pdf = await _win.webContents.printToPDF({ landscape: true, printBackground: true, pageSize: 'A4', margins: { marginType: 'custom', top: 0.4, bottom: 0.4, left: 0.4, right: 0.4 } });
    fs.mkdirSync(pasta, { recursive: true });
    fs.writeFileSync(path.join(pasta, `${nome}.pdf`), pdf);
    res.pdf = path.join(pasta, `${nome}.pdf`);
  } catch (e) { _log(`PDF do totalizador: ${e.message || e}`); }
  const baixa = _esperaDownload(40000);
  const cx = await _js(JS_CLICA('/BAIXAR XML DO (RECIBO|TOTALIZADOR)|XML DO RECIBO/')).catch(() => false);
  if (cx) {
    const d = await baixa;
    if (d.state === 'completed') {
      try { fs.copyFileSync(d.dest, path.join(pasta, `${nome}.xml`)); res.xml = path.join(pasta, `${nome}.xml`); fs.unlink(d.dest, () => {}); } catch (e) { _log(`XML do totalizador: ${e.message || e}`); }
    }
  } else if (_espera) _espera = null;
  _log(`R-${ev}: recibo ${res.recibo} · ${res.porCodigo.length} código(s) de receita${res.pdf ? ' · PDF salvo' : ''}${res.xml ? ' · XML salvo' : ''}`);
  await _js(JS_CLICA('/^VOLTAR$/')).catch(() => false);
  await _sleep(1500);
  return res;
}

// ------------------------------------------------------------------ empresas e nuvem
function _pastaEmp(emp, comp) {
  const [a, m] = comp.split('-');
  const p = pastaCliente.pastaDoMes({ nome: emp.nome, cnpj: emp.cnpj }, a, m, true);
  return p || path.join(D.userData(), 'EFD-Reinf', comp, String(emp.nome || emp.cnpj).replace(/[\\/:*?"<>|]+/g, ' ').trim());
}
async function _docAnterior(comp, cnpj) {
  try { const { db, f } = _fs(); const d = await f.getDoc(f.doc(db, COL, `${comp}_${cnpj}`)); return d.exists() ? d.data() : null; } catch (_) { return null; }
}
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

// dados de uma competência (todas as empresas) + a anterior, para a conferência "enviou no mês passado e não neste"
async function dados(comp) {
  const { db, f } = _fs();
  const [ca, cm] = comp.split('-').map(Number);
  const ant = cm === 1 ? `${ca - 1}-12` : `${ca}-${String(cm - 1).padStart(2, '0')}`;
  const ler = async (c) => {
    const out = [];
    const q = f.query(f.collection(db, COL), f.where('comp', '==', c));
    (await f.getDocs(q)).forEach((x) => out.push(x.data()));
    return out;
  };
  const [atual, anterior, emps, meta] = await Promise.all([ler(comp), ler(ant).catch(() => []), empresas(), f.getDoc(f.doc(db, COL, `_meta_${comp}`)).catch(() => null)]);
  return { comp, anterior: ant, empresas: emps, docs: atual, docsAnterior: anterior.map((x) => ({ cnpj: x.cnpj, status: x.status, nEventos: (x.eventos || []).length })),
    meta: meta && meta.exists() ? meta.data() : null, rodando: _rodando, certificado: cnpjCertificado() };
}

// ------------------------------------------------------------------ conferência
async function _empresa(emp, comp) {
  const ant = await _docAnterior(comp, emp.cnpj);
  const lidos = new Map(((ant && ant.eventos) || []).filter((x) => x.recibo && x.evento).map((x) => [x.recibo, x]));
  const p = await _perfil(emp);
  if (p.semProcuracao) return { status: 'sem_procuracao', msg: p.msg ? `o eCAC respondeu: ${p.msg.toLowerCase()}` : 'A Liddera não tem procuração eletrônica desta empresa para a EFD-Reinf (ou ela venceu).' };
  if (p.erro) return { status: 'erro', msg: p.erro };
  await _abreReinf();
  const pasta = _pastaEmp(emp, comp);
  const pastaXml = path.join(pasta, `EFD-Reinf ${comp.slice(5, 7)}${comp.slice(0, 4)}`);
  const eventos = [], avisos = [], falhaLista = {};
  const fech = {};
  for (const serie of ['4000', '2000']) {
    if (_parar) break;
    _prog(`${emp.nome}: lendo a série R-${serie}…`);
    const l = await _lista(serie, comp);
    if (l.erro || l.aviso) { avisos.push(l.erro || l.aviso); falhaLista[serie] = l.erro || l.aviso; _log(`${emp.nome} R-${serie}: ${l.erro || l.aviso}`); }
    const rows = (l.rows || []).filter((r) => r.recibo);
    const novos = [];
    for (const r of rows) {
      const ja = lidos.get(r.recibo);
      if (ja) { eventos.push({ ...ja, recepcao: r.recepcao || ja.recepcao, tipo: /RETIF/i.test(r.tipo) ? 'Retificador' : ja.tipo }); continue; }
      if (_parar) break;
      _prog(`${emp.nome}: R-${serie} · evento ${eventos.length + novos.length + 1} de ${rows.length}…`);
      const arq = r.det ? await _xmlEvento(r, serie, comp) : null;
      if (arq) {
        const dest = path.join(pastaXml, `${r.recibo.replace(/[^\w-]+/g, '_')}.xml`);
        try { fs.mkdirSync(pastaXml, { recursive: true }); fs.copyFileSync(arq, dest); fs.unlink(arq, () => {}); novos.push({ r, dest }); }
        catch (e) { novos.push({ r, dest: arq }); }
      } else {
        eventos.push({ evento: serie === '4000' ? 'R-40xx' : 'R-20xx', recibo: r.recibo, recepcao: r.recepcao, tipo: /RETIF/i.test(r.tipo) ? 'Retificador' : 'Original', benef: r.benef, est: r.est, semXml: true });
      }
    }
    const lidosXml = await _lerXmls(novos.map((x) => x.dest));
    novos.forEach((n, i) => {
      const x = lidosXml[i] || {};
      eventos.push({ evento: x.evento || (serie === '4000' ? 'R-40xx' : 'R-20xx'), recibo: n.r.recibo, recepcao: n.r.recepcao, tipo: x.tipo || (/RETIF/i.test(n.r.tipo) ? 'Retificador' : 'Original'),
        benef: x.benef || n.r.benef, est: n.r.est, natRend: x.natRend || [], bruto: x.bruto || 0, irrf: x.irrf || 0, csll: x.csll || 0, cofins: x.cofins || 0, pis: x.pis || 0,
        agreg: x.agreg || 0, inss: x.inss || 0, pagamentos: (x.pagamentos || []).slice(0, 40), xml: n.dest });
    });
    if (_parar) break;
    _prog(`${emp.nome}: fechamento R-${serie === '4000' ? '4099' : '2099'}…`);
    fech[serie] = await _fechamento(serie, comp, emp, pasta).catch((e) => ({ fechado: false, aviso: String(e.message || e) }));
    if (fech[serie].aviso) avisos.push(fech[serie].aviso);
  }
  // totais: do totalizador (o que foi para a DCTFWeb); período aberto: soma dos eventos
  const ks = ['irrf', 'csll', 'cofins', 'pis', 'agreg', 'inss'];
  const totais = Object.fromEntries(ks.map((k) => [k, 0]));
  const somaEv = Object.fromEntries(ks.map((k) => [k, Math.round(eventos.reduce((s, x) => s + (x[k] || 0), 0) * 100) / 100]));
  const doTot = { '4000': !!(fech['4000'] && fech['4000'].fechado && fech['4000'].porCodigo.length), '2000': !!(fech['2000'] && fech['2000'].fechado && fech['2000'].porCodigo.length) };
  for (const serie of ['4000', '2000']) {
    const fx = fech[serie];
    if (doTot[serie]) fx.porCodigo.forEach((x) => { x.imposto = _imposto(x.cod, serie); totais[x.imposto] += x.enviado; });
    else (serie === '4000' ? ['irrf', 'csll', 'cofins', 'pis', 'agreg'] : ['inss']).forEach((k) => { totais[k] += somaEv[k]; });
  }
  ks.forEach((k) => { totais[k] = Math.round(totais[k] * 100) / 100; });
  const f4 = fech['4000'] || {}, f2 = fech['2000'] || {};
  const temEv = eventos.length > 0;
  const fechado = !!(f4.fechado || f2.fechado);
  let status = fechado ? (temEv ? 'fechado' : 'sem_movimento') : temEv ? 'aberto' : 'nada_enviado';
  if (status === 'nada_enviado' && falhaLista['4000']) {
    return { status: 'erro', msg: `não consegui ler a REINF desta empresa no eCAC (${falhaLista['4000']})`, eventos, avisos, pasta };
  }
  // série com evento e sem fechamento, mesmo com a outra fechada: continua aberto
  const abertaSerie = (eventos.some((x) => /^R-40/.test(x.evento)) && !f4.fechado) || (eventos.some((x) => /^R-20/.test(x.evento)) && !f2.fechado);
  return { status: status === 'fechado' && abertaSerie ? 'aberto' : status, eventos, totais, somaEventos: somaEv, fech4099: f4, fech2099: f2, avisos, pasta };
}
function _imposto(cod, serie) {
  if (serie === '2000') return 'inss';
  return { 6228: 'csll', 5987: 'csll', 6230: 'pis', 5979: 'pis', 6243: 'cofins', 5960: 'cofins', 5952: 'agreg' }[String(cod).slice(0, 4)] || 'irrf';
}

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
  try {
    const { db, f } = _fs();
    await f.setDoc(f.doc(db, COL, `_meta_${comp}`), { rodando: true, inicio: new Date().toISOString(), por: s.nome || s.email || '', maquina: os.hostname(), auto: !!auto }, { merge: true }).catch(() => {});
    _janela();
    await _login();
    for (const [n, emp] of lista.entries()) {
      if (_parar) break;
      _prog(`${emp.nome} (${n + 1} de ${lista.length})…`, { feitas: n, total: lista.length });
      _log(`===== ${emp.nome} (${_fmtCnpj(emp.cnpj)}) · ${comp}`);
      let r;
      try { r = await _empresa(emp, comp); } catch (e) { r = { status: 'erro', msg: String(e.message || e).slice(0, 300) }; await _print(); }
      if (_certFaltou) throw new Error(`o certificado do escritório não está instalado no Windows deste computador.`);
      if (r.status === 'erro') res.erros++; else res.ok++;
      await _grava(comp, emp, r).catch((e) => _log(`gravar na nuvem: ${e.message || e}`));
      try { D.notificar('reinf:empresa', { comp, cnpj: emp.cnpj }); } catch (_) {}
    }
    await f.setDoc(f.doc(db, COL, `_meta_${comp}`), { rodando: false, fim: new Date().toISOString(), por: s.nome || s.email || '', maquina: os.hostname(), auto: !!auto, ok: res.ok, erros: res.erros, total: lista.length }, { merge: true }).catch(() => {});
    // REINF × DCTFWeb: o computador do Integra Contador confere a DCTFWeb das empresas que acabaram de ser conferidas
    if (!_parar) { try { await require('./dctfweb').pedirAuto(comp, cnpjs && cnpjs.length ? lista.map((x) => x.cnpj) : []); } catch (_) {} }
  } finally {
    _rodando = false;
    try { if (_vivo()) _win.destroy(); } catch (_) {}
    _win = null;
    _prog('', { fim: true });
  }
  return res;
}
function parar() { _parar = true; if (_espera) { const w = _espera; _espera = null; w({ state: 'cancelado' }); } return { ok: true }; }
const ocupado = () => _rodando;

module.exports = { init, podeUsar, conferir, parar, dados, empresas, salvarEmpresas, certificadoInstalado, ocupado, cnpjCertificado, MODULO };
