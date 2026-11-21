'use strict';
// EFD-Reinf pelo eCAC, COM A PESSOA (2.4.17) — pedido do Rafael, 21/11/2026.
//
// Os valores da REINF (eventos e o totalizador do fechamento R-4099/R-2099, que é o que vai para a DCTFWeb) só aparecem
// no eCAC. Desde 21/11 a Receita recusa a troca de perfil feita pelo sistema ("a execução possui atributos que caracteriza
// acesso automatizado"). O sistema NÃO contorna isso: quem clica em "Alterar" no "Alterar perfil de acesso" é a pessoa.
//   1. o sistema entra no eCAC com o e-CNPJ do escritório (gov.br › Seu certificado digital; captcha/autorização: a pessoa);
//   2. abre "Alterar perfil de acesso" e preenche o CNPJ em "Procurador de pessoa jurídica - CNPJ";
//   3. a janela aparece com uma faixa "clique em Alterar"; a PESSOA clica (e resolve o desafio do hCaptcha, se vier);
//      fechar o quadro pula a empresa; sem ninguém por 4 minutos, a leitura pelo eCAC para (o resto fica para depois);
//   4. com o perfil trocado, o sistema abre a EFD-Reinf, baixa os XMLs dos eventos e lê o totalizador (PDF + XML na pasta
//      do cliente), como na 2.4.6;
//   5. mensagem importante na Caixa Postal ("é necessário que você leia…"): o sistema NÃO abre (abrir dá ciência da
//      intimação — Decreto 70.235/1972, art. 23, § 2º, III, "b"); marca a empresa e sai desse perfil (entra de novo).
// Só é chamado para as empresas com fechamento NOVO na consulta oficial (recibo ainda não lido): um clique por empresa
// por mês, no máximo.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, BrowserWindow, session } = require('electron');
const pastaCliente = require('./pasta_cliente');

const URL_LOGIN = 'https://cav.receita.fazenda.gov.br/autenticacao/login';
const URL_ECAC = 'https://cav.receita.fazenda.gov.br/ecac/';
const URL_REINF = 'https://www3.cav.receita.fazenda.gov.br/reinfweb/#/home';
const PARTICAO = 'persist:reinf-ecac';
const ESPERA_CLIQUE = 4 * 60000;

let D = null;      // { userData(), janelaPai(), runFiscal(args, out), log(m), prog(t, x), cnpjCertificado(), parando() }
let _win = null, _rodando = false, _certFaltou = false, _espera = null, _baixando = false, _rede = [];
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');
const _fmtCnpj = (c) => _so(c).replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
const _vivo = () => _win && !_win.isDestroyed();
const _log = (m) => D.log(`[eCAC] ${m}`);
const _prog = (t, x) => D.prog(t, x);
const _parar = () => !!(D.parando && D.parando());
async function _print() { try { if (_vivo()) fs.writeFileSync(path.join(D.userData(), 'reinf_ultima.png'), (await _win.webContents.capturePage()).toPNG()); } catch (_) {} }
const cnpjCertificado = () => D.cnpjCertificado();

function _cnpjCert(c) {
  const cn = String((c.subject && c.subject.commonName) || c.subjectName || '');
  const m = cn.match(/:(\d{14})\b/) || String(c.subjectName || '').match(/(?<!\d)(\d{14})(?!\d)/);
  return m ? m[1] : '';
}
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

// ------------------------------------------------------------------ janela
function _janela() {
  if (_vivo()) return _win;
  const pai = D.janelaPai && D.janelaPai();
  _win = new BrowserWindow({ show: false, width: 1280, height: 880, title: 'FiscoCont+ · EFD-Reinf · clique em "Alterar"', autoHideMenuBar: true,
    parent: pai && !pai.isDestroyed() ? pai : undefined,
    webPreferences: { partition: PARTICAO, contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
  const ses = session.fromPartition(PARTICAO);
  _win.webContents.setWindowOpenHandler(({ url }) => { _log(`o site quis abrir janela nova: ${String(url).slice(0, 120)} → mesma janela`); _win.loadURL(url).catch(() => {}); return { action: 'deny' }; });
  _win.webContents.on('did-navigate', (_e, url) => _log(`abriu ${String(url).split('?')[0]}`));
  _win.webContents.on('did-navigate-in-page', (_e, url) => _log(`tela ${String(url).split('?')[0].slice(-80)}`));
  _win.webContents.on('did-fail-load', (_e, cod, desc, url) => { if (cod !== -3) _log(`falha ao abrir ${String(url).split('?')[0]}: ${desc} (${cod})`); });
  _win.webContents.on('dom-ready', () => { _win.webContents.executeJavaScript('window.alert = (m) => console.log("alerta:", m);').catch(() => {}); });
  _win.webContents.on('console-message', (_e, _n, msg) => { if (/^alerta:/.test(msg)) _log(`aviso do site: ${msg.slice(8, 300)}`); });
  _win.on('close', (ev) => { if (_rodando && !_parar()) { ev.preventDefault(); _win.hide(); } });
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
    // endereços das chamadas da EFD-Reinf (para ajustar a leitura ao site real); nada de conteúdo
    ses.webRequest.onCompleted((det) => {
      if (!/reinfweb|cav\.receita/.test(det.url) || !/xhr|fetch/i.test(det.resourceType || '')) return;
      _rede.push(`${new Date().toLocaleTimeString('pt-BR')} ${det.method} ${det.statusCode} ${String(det.url).split('?')[0].slice(0, 160)}`);
      try { fs.writeFileSync(path.join(D.userData(), 'reinf_ecac_rede.txt'), _rede.slice(-600).join('\n')); } catch (_) {}
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
// gov.br › "Seu certificado digital". Achado real (20/11): o sistema procurou 2 s depois de a página abrir e não achou
// (as opções aparecem depois e podem ser <div>/<p> com onclick). Agora: identificador da opção, depois o texto em
// qualquer elemento (o mais interno), e devolve a posição para o clique com o mouse se o clique comum não abrir.
const JS_CERT_GOVBR = (modo) => `(() => { ${JS_BASE}
  const ruim = (x) => /NUVEM|CLOUD/.test(txt(x)) || /cloud|nuvem/i.test((x.id || '') + ' ' + (x.className || ''));
  let alvo = [...document.querySelectorAll('#login-certificate, [id*="certificate" i], [id*="certificado" i], a[href*="certificado.sso.acesso.gov.br"], [onclick*="certificado" i], [onclick*="certificate" i]')]
    .filter(vis).filter((x) => !ruim(x))[0];
  if (!alvo) {
    const el = [...document.querySelectorAll('a, button, [role=button], [onclick], li, label, p, span, div, img')].filter(vis)
      .filter((x) => /(^|SEU )CERTIFICADO DIGITAL$/.test(txt(x)) && !ruim(x) && txt(x).length < 40)
      .filter((x, _i, l) => !l.some((y) => y !== x && x.contains(y)))[0];
    if (el) alvo = el.closest('a, button, [role=button], [onclick], li') || el;
  }
  if (!alvo) return false;
  alvo.scrollIntoView({ block: 'center' });
  const b = alvo.getBoundingClientRect();
  if (${JSON.stringify(modo)} === 'clica') alvo.click();
  return { t: (txt(alvo) || alvo.id || alvo.tagName).slice(0, 60), x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2) };
})()`;
const JS_DIAG_GOV = `(() => { const out = [];
  document.querySelectorAll('a, button, [onclick], li, div, p, span, img').forEach((x) => { if (x.children.length > 4) return; const h = x.outerHTML; if (/certificad/i.test(h) && out.length < 12) out.push(h.replace(/\\s+/g, ' ').slice(0, 220)); });
  return out.join(' || '); })()`;
// "Alterar perfil de acesso" › Procurador de pessoa jurídica - CNPJ
const JS_PERFIL = (cnpj, modo) => `(() => { ${JS_BASE}
  // o rótulo mais interno (o próprio texto, não a caixa que também o contém — senão pegava o campo do CPF de cima)
  const reP = /PROCURADOR DE PESSOA JURIDICA|PROCURADOR.{0,25}CNPJ|PESSOA JURIDICA.{0,10}CNPJ/;
  const rot = [...document.querySelectorAll('label, span, div, td, th, p, h3, h4, h5, legend, strong, b, option')].filter(vis).filter((x) => reP.test(txt(x)) && txt(x).length < 80)
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
  if (m === 'valor' || m === 'poe') setVal(inp, '${cnpj}');
  if (m === 'poe') return { ok: true, campo: inp.value };
  if (m === 'clica' || m === 'valor') { bt.click(); return { ok: true, campo: inp.value }; }
  return { ok: true, campo: inp.value };
})()`;
// diagnóstico da janela "Alterar perfil de acesso" (em cada quadro): endereço, rótulos e campos — vai para o passo a passo
const JS_DIAG_PERFIL = `(() => { const v = (e) => e.getClientRects().length > 0;
  const rot = [...document.querySelectorAll('label, span, td, th, p, h3, h4, h5, legend, strong, b, a, button')].filter(v)
    .map((e) => (e.innerText || '').replace(/\\s+/g, ' ').trim()).filter((t) => t && t.length < 70 && /PROCURAD|PERFIL|CNPJ|CPF|ALTERAR|JUR[IÍ]DICA|REPRESENT|RESPONS/i.test(t));
  const inp = [...document.querySelectorAll('input, select')].filter(v).map((e) => [e.tagName.toLowerCase(), e.type, e.id, e.name, e.placeholder].filter(Boolean).join(':'));
  return location.href.split('?')[0] + ' | rótulos: ' + [...new Set(rot)].slice(0, 14).join(' ; ') + ' | campos: ' + inp.slice(0, 12).join(' , '); })()`;
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


// faixa do FiscoCont+ em cima do quadro "Alterar perfil de acesso" e destaque no botão Alterar do procurador PJ
const JS_FAIXA_PERFIL = (nome, n, tot) => `(() => { ${JS_BASE}
  if (!document.getElementById('fcFaixaP')) {
    const st = document.createElement('style'); st.id = 'fcEstiloP';
    st.textContent = '#fcFaixaP{position:fixed;top:0;left:0;right:0;z-index:2147483001;background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:12px 18px;font:14px/1.4 "Segoe UI",system-ui,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.25)}'
      + '#fcFaixaP b{font-size:15px}#fcFaixaP span{display:block;opacity:.92;font-size:12.5px;margin-top:2px}.fc-alt{outline:3px solid #f59e0b!important;outline-offset:3px!important;box-shadow:0 0 0 6px rgba(245,158,11,.25)!important}';
    document.head.appendChild(st);
    const f = document.createElement('div'); f.id = 'fcFaixaP'; document.body.appendChild(f);
  }
  document.getElementById('fcFaixaP').innerHTML = '<b>Conferência da EFD-Reinf · ' + ${JSON.stringify(`${n} de ${tot}`)} + '</b><span>O CNPJ de <b>' + ${JSON.stringify(nome)} + '</b> já está preenchido: clique em <b>Alterar</b> (ao lado de "Procurador de pessoa jurídica - CNPJ"). Para pular esta empresa, feche o quadro.</span>';
  return true;
})()`;
const JS_DESTACA_ALTERAR = (cnpj) => `(() => { ${JS_BASE}
  const reP = /PROCURADOR DE PESSOA JURIDICA|PROCURADOR.{0,25}CNPJ|PESSOA JURIDICA.{0,10}CNPJ/;
  const rot = [...document.querySelectorAll('label, span, div, td, th, p, h3, h4, h5, legend, strong, b, option')].filter(vis).filter((x) => reP.test(txt(x)) && txt(x).length < 80)
    .filter((x) => ![...x.children].some((c) => reP.test(txt(c))))[0];
  if (!rot) return false;
  let box = rot, bt = null;
  for (let i = 0; i < 5 && box && !bt; i++) { box = box.parentElement; bt = [...box.querySelectorAll('input[type=button], input[type=submit], button, a')].filter(vis).find((b) => /^ALTERAR$/.test(txt(b))); }
  if (bt) { bt.classList.add('fc-alt'); bt.scrollIntoView({ block: 'center' }); }
  return !!bt;
})()`;
const JS_TIRA_FAIXA_P = `(() => { ['fcEstiloP', 'fcFaixaP'].forEach((i) => { const e = document.getElementById(i); if (e) e.remove(); }); document.querySelectorAll('.fc-alt').forEach((e) => e.classList.remove('fc-alt')); })()`;
// aviso de mensagem importante na Caixa Postal (trava o eCAC até ser lida): só detecta, nunca clica
const JS_CAIXA_POSTAL = `(() => { ${JS_BASE}
  const t = norm(document.body ? document.body.innerText : '');
  return /MENSAGENS? IMPORTANTES?/.test(t) && /CAIXA POSTAL/.test(t) && /NECESSARIO QUE VOCE LEIA|AINDA NAO LIDAS/.test(t);
})()`;
// o que há para clicar na tela (para o passo a passo, quando um menu não é achado)
const JS_DIAG_MENU = `(() => { ${JS_BASE}
  return [...new Set(clicaveis().map((x) => txt(x)).filter((t) => t && t.length < 70))].slice(0, 60).join(' | '); })()`;

// ------------------------------------------------------------------ passos
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
  while (Date.now() < fim && _vivo() && !_parar()) {
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

// login com o certificado do escritório. Sem clique "simulado com o mouse" nem chamada direta do hCaptcha: se o botão
// do gov.br ou a opção do certificado não andarem com o clique comum, a janela aparece e a pessoa clica.
async function _login() {
  _prog('Entrando no eCAC com o certificado do escritório…');
  await _vai(URL_ECAC);
  if (/cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url()) && !/autenticacao/.test(_url())) { _log('sessão do eCAC ainda aberta'); return; }
  if (!/autenticacao\/login/.test(_url())) await _vai(URL_LOGIN);
  for (let tent = 0; tent < 2 && !/sso\.acesso\.gov\.br/.test(_url()); tent++) {
    await _sleep(1500);
    const t = await _js(JS_GOVBR('clica')).catch(() => false);
    _log(`login: ${t ? `clicou em "${t}"` : 'botão gov.br não encontrado'}`);
    if (!t && tent === 0) _log(`login · página: ${await _js(JS_DIAG).catch(() => '')}`);
    for (let i = 0; i < 16 && !/sso\.acesso\.gov\.br/.test(_url()); i++) await _sleep(500);
    await _pronto();
    if (!/sso\.acesso\.gov\.br/.test(_url())) await _humano('login do eCAC');
  }
  if (!/sso\.acesso\.gov\.br|cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url())) await _pessoaClica('Clique em "Entrar com gov.br" e depois em "Seu certificado digital".', () => /sso\.acesso\.gov\.br|cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url()));
  if (/sso\.acesso\.gov\.br/.test(_url())) {
    await _humano('gov.br (antes do certificado)');
    let c = false;
    for (let k = 0; k < 20 && !c && /sso\.acesso\.gov\.br/.test(_url()); k++) {
      c = await _js(JS_CERT_GOVBR('clica')).catch(() => false);
      if (!c) await _sleep(750);
    }
    _log(`gov.br: ${c ? `clicou em "${c.t}"` : 'opção do certificado não encontrada'}`);
    if (!c) _log(`gov.br · página: ${await _js(JS_DIAG_GOV).catch(() => '')}`);
    for (let i = 0; i < 10 && /sso\.acesso\.gov\.br\/(login)?(\?|$|#)/.test(_url()); i++) await _sleep(500);
    if (/sso\.acesso\.gov\.br\/(login)?(\?|$|#)/.test(_url())) await _pessoaClica('Clique em "Seu certificado digital".', () => !/sso\.acesso\.gov\.br\/(login)?(\?|$|#)/.test(_url()));
    await _pronto(45000);
  }
  for (let i = 0; i < 40; i++) {
    if (_certFaltou) throw new Error(`o certificado do escritório (e-CNPJ ${_fmtCnpj(cnpjCertificado())}) não está instalado no Windows deste computador.`);
    if (/cav\.receita\.fazenda\.gov\.br\/ecac/i.test(_url())) { _log('eCAC aberto'); return; }
    if (await _humano('gov.br')) continue;
    await _sleep(1500);
  }
  await _print();
  throw new Error('não consegui entrar no eCAC (veja o "Passo a passo").');
}
// mostra a janela e espera a pessoa fazer o passo (até 4 minutos)
async function _pessoaClica(texto, pronto) {
  _log(`esperando a pessoa: ${texto}`);
  _prog(`eCAC: ${texto} (na janela que abriu)`, { humano: true });
  _mostra(true);
  const fim = Date.now() + ESPERA_CLIQUE;
  while (Date.now() < fim && _vivo() && !_parar()) { if (await pronto()) break; await _sleep(800); }
  _mostra(false);
}

async function _novaSessao() {
  try {
    const ses = session.fromPartition(PARTICAO);
    await ses.clearStorageData({ origins: ['https://cav.receita.fazenda.gov.br', 'https://www3.cav.receita.fazenda.gov.br'] });
    await ses.clearStorageData({ storages: ['cookies'] }).catch(() => {});
  } catch (e) { _log(`limpar a sessão: ${e.message || e}`); }
  await _login();
}

// troca o perfil para a empresa COM A PESSOA clicando em Alterar.
// Devolve { ok } · { semProcuracao, msg } · { caixaPostal } · { pulada } · { semPessoa } · { erro }
async function _perfil(emp, n, tot) {
  const norm = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  await _vai(URL_ECAC);
  if (/autenticacao|sso\.acesso/.test(_url())) { _log('a sessão do eCAC caiu: entrando de novo'); await _login(); await _vai(URL_ECAC); }
  if (await _js(JS_CAIXA_POSTAL).catch(() => false)) { _log('aviso da Caixa Postal do perfil anterior: entrando de novo (sem abrir a mensagem)'); await _novaSessao(); await _vai(URL_ECAC); }
  await _portalAntigo();
  await _js(JS_CLICA('/^(OK|FECHAR|X)$/')).catch(() => false);
  let ab = await _js(JS_CLICA('/ALTERAR PERFIL/')).catch(() => false);
  if (!ab) { ab = await _js(JS_ABRE_PERFIL).catch(() => false); if (ab && /^menu:/.test(ab)) { await _sleep(1000); ab = await _js(JS_ABRE_PERFIL).catch(() => false); } }
  if (!ab) { await _print(); return { erro: '"Alterar perfil de acesso" não encontrado no eCAC.' }; }
  let achou = { r: null, fr: null };
  for (let k = 0; k < 16 && !achou.fr; k++) { await _sleep(750); achou = await _nosQuadros(JS_PERFIL(_so(emp.cnpj), 'acha')); }
  if (!achou.fr) {
    const diag = [];
    for (const fr of _win.webContents.mainFrame.framesInSubtree) { try { diag.push(await fr.executeJavaScript(JS_DIAG_PERFIL, true)); } catch (_) {} }
    _log(`${emp.nome}: janela "Alterar perfil" · ${diag.join(' || ').slice(0, 1500)}`);
    await _print(); return { erro: (achou.r && achou.r.motivo) || 'campo do procurador não encontrado' };
  }
  const fr = achou.fr;
  // o sistema só PREENCHE o CNPJ; quem clica em Alterar é a pessoa
  await fr.executeJavaScript(JS_PERFIL(_so(emp.cnpj), 'poe'), true).catch(() => null);
  await fr.executeJavaScript(JS_DESTACA_ALTERAR(_so(emp.cnpj)), true).catch(() => false);
  await _js(JS_FAIXA_PERFIL(emp.nome, n, tot)).catch(() => false);
  _log(`${emp.nome}: CNPJ preenchido · esperando a pessoa clicar em "Alterar"`);
  _prog(`eCAC · ${emp.nome} (${n} de ${tot}): clique em "Alterar" na janela que abriu.`, { humano: true });
  _mostra(true);
  const fim = Date.now() + ESPERA_CLIQUE;
  let semQuadro = 0, ultMsg = '';
  try {
    while (Date.now() < fim) {
      if (!_vivo()) return { erro: 'a janela do eCAC foi fechada.' };
      if (_parar()) return { pulada: true, msg: 'conferência parada' };
      await _sleep(800);
      const t = norm(await _js(JS_TEXTO).catch(() => ''));
      if (/PROCURADOR DE:?/.test(t) && t.includes(_fmtCnpj(emp.cnpj))) {
        await _pronto(); await _sleep(1200);
        if (await _js(JS_CAIXA_POSTAL).catch(() => false)) { _log(`${emp.nome}: mensagem importante na Caixa Postal (não aberta)`); return { caixaPostal: true }; }
        await _portalAntigo();
        _log(`${emp.nome}: perfil de procurador ok (clique da pessoa)`);
        return { ok: true };
      }
      let msg = '';
      for (const q of _win.webContents.mainFrame.framesInSubtree) { const m2 = norm(await q.executeJavaScript(JS_MSG_PERFIL, true).catch(() => '')); if (m2) { msg = m2; break; } }
      if (msg && msg !== ultMsg) { ultMsg = msg; _log(`${emp.nome}: o eCAC respondeu "${msg}"`); }
      if (/PROCURAC/.test(msg) && /(NAO|INEXIST|SEM|EXPIRAD|VENCID|CANCELAD)/.test(msg)) return { semProcuracao: true, msg };
      // a pessoa fechou o quadro sem trocar: pula a empresa
      const aberto = (await _nosQuadros(JS_PERFIL(_so(emp.cnpj), 'acha'))).fr;
      semQuadro = aberto ? 0 : semQuadro + 1;
      if (semQuadro >= 4) { _log(`${emp.nome}: o quadro foi fechado · empresa pulada`); return { pulada: true, msg: 'pulada na troca de perfil' }; }
    }
    _log(`${emp.nome}: ninguém clicou em "Alterar" em 4 minutos`);
    return { semPessoa: true };
  } finally {
    _mostra(false);
    for (const q of (_vivo() ? _win.webContents.mainFrame.framesInSubtree : [])) await q.executeJavaScript(JS_TIRA_FAIXA_P, true).catch(() => {});
  }
}

async function _portalAntigo() {
  // achado real (vídeo de 21/11): depois do login aparece "Atenção · Prepare-se para a evolução dos serviços digitais da
  // RFB" com "Continuar no e-CAC por enquanto" / "Acessar o portal Serviços da Receita Federal". Fica no e-CAC.
  let ev = await _js(JS_CLICA('/CONTINUAR NO E-?CAC/')).catch(() => false);
  if (!ev) for (const q of _win.webContents.mainFrame.framesInSubtree) { ev = await q.executeJavaScript(JS_CLICA('/CONTINUAR NO E-?CAC/'), true).catch(() => false); if (ev) break; }
  if (ev) { _log(`aviso da Receita: clicou em "${ev}"`); await _sleep(900); }
  const t = (await _js(JS_TEXTO).catch(() => '')).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  if (/NOVO/.test(t) && /ANTIG/.test(t) && /(PORTAL|VERSAO|ECAC)/.test(t)) {
    const c = await _js(JS_CLICA('/ANTIG|VERSAO (ANTERIOR|CLASSICA)|CONTINUAR (NO|NA) (ATUAL|VERSAO ATUAL)/')).catch(() => false);
    if (c) { _log(`portal antigo: "${c}"`); await _pronto(); }
  }
}

// roda o script em cada quadro da página (a janela "Alterar perfil" pode vir dentro de um iframe) e devolve o primeiro
// quadro em que ele respondeu ok. Achado (21/11): procurava só na página principal → "campo não encontrado".
async function _nosQuadros(codigo) {
  let primeiro = null;
  for (const fr of _win.webContents.mainFrame.framesInSubtree) {
    try { const r = await fr.executeJavaScript(codigo, true); if (r && r.ok) return { r, fr }; if (!primeiro) primeiro = r; } catch (_) {}
  }
  return { r: primeiro, fr: null };
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

function _imposto(cod, serie) {
  const c = String(cod).slice(0, 4);
  if (['1656', '1646', '1213'].includes(c)) return 'funrural';           // Funrural do R-2055 (CP, GILRAT, Senar)
  if (serie === '2000') return 'inss';
  return { 6228: 'csll', 5987: 'csll', 6230: 'pis', 5979: 'pis', 6243: 'cofins', 5960: 'cofins', 5952: 'agreg' }[c] || 'irrf';
}

// ------------------------------------------------------------------ leitura de UMA empresa (perfil já trocado)
async function _leReinf(emp, comp, ant) {
  const lidos = new Map(((ant && ant.eventos) || []).filter((x) => x.recibo && x.evento && !x.semXml).map((x) => [x.recibo, x]));
  await _abreReinf();
  const pasta = _pastaEmp(emp, comp);
  const pastaXml = path.join(pasta, `EFD-Reinf ${comp.slice(5, 7)}${comp.slice(0, 4)}`);
  const eventos = [], avisos = [];
  const fech = {};
  for (const serie of ['4000', '2000']) {
    if (_parar()) break;
    _prog(`${emp.nome}: lendo a série R-${serie} no eCAC…`);
    const l = await _lista(serie, comp);
    if (l.erro || l.aviso) {
      avisos.push(l.erro || l.aviso);
      _log(`${emp.nome} R-${serie}: ${l.erro || l.aviso} · tela: ${(await _js(JS_DIAG_MENU).catch(() => '')).slice(0, 900)}`);
    }
    const rows = (l.rows || []).filter((r) => r.recibo);
    const novos = [];
    for (const r of rows) {
      const ja = lidos.get(r.recibo);
      if (ja) { eventos.push({ ...ja, recepcao: r.recepcao || ja.recepcao, tipo: /RETIF/i.test(r.tipo) ? 'Retificador' : ja.tipo }); continue; }
      if (_parar()) break;
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
    if (_parar()) break;
    _prog(`${emp.nome}: totalizador do R-${serie === '4000' ? '4099' : '2099'}…`);
    fech[serie] = await _fechamento(serie, comp, emp, pasta).catch((e) => ({ fechado: false, aviso: String(e.message || e) }));
    if (fech[serie].aviso) avisos.push(fech[serie].aviso);
  }
  // totais: do totalizador (o que foi para a DCTFWeb); sem totalizador, a soma dos eventos
  const ks = ['irrf', 'csll', 'cofins', 'pis', 'agreg', 'inss', 'funrural'];
  const totais = Object.fromEntries(ks.map((k) => [k, 0]));
  const somaEv = Object.fromEntries(ks.map((k) => [k, Math.round(eventos.reduce((s, x) => s + (x[k] || 0), 0) * 100) / 100]));
  for (const serie of ['4000', '2000']) {
    const fx = fech[serie];
    if (fx && fx.fechado && (fx.porCodigo || []).length) fx.porCodigo.forEach((x) => { x.imposto = _imposto(x.cod, serie); totais[x.imposto] += x.enviado; });
    else (serie === '4000' ? ['irrf', 'csll', 'cofins', 'pis', 'agreg'] : ['inss']).forEach((k) => { totais[k] += somaEv[k]; });
  }
  ks.forEach((k) => { totais[k] = Math.round(totais[k] * 100) / 100; });
  const temTot = ['4000', '2000'].some((s) => fech[s] && fech[s].fechado && (fech[s].porCodigo || []).length);
  return { eventos, totais, somaEventos: somaEv, fech4099: fech['4000'] || {}, fech2099: fech['2000'] || {}, avisos, pasta, temTotalizador: temTot };
}

// ------------------------------------------------------------------ entrada: lê as empresas pedidas (com a pessoa)
// aoEmpresa(emp, resultado) é chamado a cada empresa. Devolve { lidas, puladas, parouPor }
async function ler(lista, comp, anteriores, aoEmpresa) {
  if (!lista.length) return { lidas: 0, puladas: 0 };
  _rodando = true; _certFaltou = false; _rede = [];
  const out = { lidas: 0, puladas: 0, parouPor: '' };
  try {
    _janela();
    await _login();
    for (const [i, emp] of lista.entries()) {
      if (_parar()) { out.parouPor = 'parada'; break; }
      _log(`===== ${emp.nome} (${_fmtCnpj(emp.cnpj)}) · ${comp} · valores pelo eCAC`);
      let r;
      try {
        const p = await _perfil(emp, i + 1, lista.length);
        if (p.semPessoa) { out.parouPor = 'ninguém clicou em "Alterar" em 4 minutos'; break; }
        if (p.ok) r = { ok: true, ...(await _leReinf(emp, comp, anteriores.get(emp.cnpj))) };
        else if (p.caixaPostal) { r = { caixaPostal: true }; await _novaSessao(); }
        else r = p;
      } catch (e) { r = { erro: String(e.message || e).slice(0, 300) }; await _print(); }
      if (_certFaltou) throw new Error('o certificado do escritório não está instalado no Windows deste computador.');
      if (r.ok) out.lidas++; else out.puladas++;
      await aoEmpresa(emp, r);
    }
  } finally {
    _rodando = false;
    try { if (_vivo()) _win.destroy(); } catch (_) {}
    _win = null;
  }
  return out;
}
const ocupado = () => _rodando;

module.exports = { init, ler, ocupado, _imposto };
