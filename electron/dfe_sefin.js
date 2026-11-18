'use strict';
// Baixas DF-e · SAÍDAS (NF-e e NFC-e) das empresas de RO pelo DFe-Download da SEFIN.
//
// Para cada empresa, numa janela própria (sessão separada por CNPJ):
//   1. entra com o e-CNPJ da empresa instalado no Windows (o sistema escolhe o certificado pelo CNPJ, na tela do navegador
//      e no SSO da SEFIN, aba "Acesso via cert. digital" → Entrar). Se o certificado não estiver no Windows, para e avisa;
//   2. lê "Ver Solicitações" e abre os Detalhes dos pedidos de NF-e/NFC-e para achar o do mês (tipo PERÍODO, período do mês
//      inteiro, operação com EMITIDA). Pedido já liberado (DOWNLOAD) e dentro da validade: baixa esse mesmo; pedido do mês
//      ainda em preparo: só espera; sem pedido do mês (ou expirado): abre a Nova Solicitação preenchida para a pessoa
//      conferir e confirmar;
//   3. o arquivo só sai depois do código da imagem (captcha), que a PESSOA digita — o sistema nunca resolve captcha. O
//      download é capturado, o ZIP é aberto (python dfe-extrair) e os XMLs vão para <pasta>/<MM-AAAA>/<empresa>/NF-e Saídas
//      ou NFC-e Saídas. O que já foi baixado (identificação do pedido + arquivo) não é baixado de novo.
// O passo a passo fica em dfe_ro_log.txt e o print da última tela em dfe_ro_ultima.png (pasta de dados), para ajustar o
// robô ao site real no primeiro uso.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, BrowserWindow, session } = require('electron');

const BASE = 'https://download.dfe.sefin.ro.gov.br';
const HOST = 'download.dfe.sefin.ro.gov.br';
const PARTICAO = (cnpj) => `persist:dfe-ro-${cnpj}`;
const DOCS = { nfe: 'NFE', nfce: 'NFCE' };
const NOME = { nfe: 'NF-e', nfce: 'NFC-e' };

let D = null;                 // { userData(), notificar(canal, dados), runFiscal(args, out), pastaBase() }
let _win = null, _cnpjAtivo = '', _certFaltou = false, _rodando = false, _espera = null;
let _baixando = null;                         // download em andamento: { nome, rec, total }
const _arqUrls = new Map();                   // endereços que responderam com arquivo (zip/xml) — para forçar o download se o site abrir o arquivo na tela
const _filhas = new Set();
let _capSeq = 0, _capPend = null, _parar = false;          // código da imagem pedido à pessoa (janela do FiscoCont+)
const _sessoes = new Set();

const _so = (s) => String(s || '').replace(/\D/g, '');
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _fmtCnpj = (c) => c.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
function _cnpjDoCert(c) {
  const cn = String((c.subject && c.subject.commonName) || c.subjectName || '');
  const m = cn.match(/:(\d{14})\b/) || String(c.subjectName || '').match(/(?<!\d)(\d{14})(?!\d)/);
  return m ? m[1] : '';
}

function init(deps) {
  D = deps;
  app.on('select-client-certificate', (event, webContents, url, lista, callback) => {
    if (!_win || _win.isDestroyed() || webContents.id !== _win.webContents.id) return;
    const alvo = lista.find((c) => _cnpjDoCert(c) === _cnpjAtivo);
    _log(`o site pediu certificado (${String(url).split('?')[0]}): ${lista.length} no Windows · ${alvo ? 'usando o e-CNPJ da empresa' : 'o e-CNPJ da empresa NÃO está instalado'}`);
    event.preventDefault();
    if (!alvo) _certFaltou = true;
    // sem o certificado: null (o Electron recusa undefined com "Must pass valid certificate object" e derruba o sistema)
    callback(alvo || null);
  });
}

// ------------------------------------------------------------------ estado guardado (por CNPJ e competência)
const _estPath = () => path.join(D.userData(), 'dfe-ro.json');
function lerEstado() { try { return JSON.parse(fs.readFileSync(_estPath(), 'utf-8')); } catch (_) { return {}; } }
function _gravaEstado(e) { try { fs.writeFileSync(_estPath(), JSON.stringify(e, null, 1)); } catch (_) {} }

let _logTxt = [];
function _log(m) {
  const l = `${new Date().toLocaleTimeString('pt-BR')} ${m}`;
  _logTxt.push(l);
  try { fs.writeFileSync(path.join(D.userData(), 'dfe_ro_log.txt'), _logTxt.slice(-600).join('\n')); } catch (_) {}
}
function _prog(txt, extra) { try { D.notificar('dfe:progresso', { txt, ...(extra || {}) }); } catch (_) {} }

// ------------------------------------------------------------------ janela
function _janela(emp) {
  if (_win && !_win.isDestroyed()) return _win;
  // a página da SEFIN fica escondida: o código da imagem aparece numa janela do próprio FiscoCont+ (pedido do Rafael, 17/11)
  _win = new BrowserWindow({ show: false, width: 1250, height: 880, title: `FiscoCont+ · DFe-Download SEFIN-RO · ${emp.nome}`, autoHideMenuBar: true,
    webPreferences: { partition: PARTICAO(emp.cnpj), contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
  _ligaImagens(_win.webContents);
  // achado real (17/11): depois do código, o site abre o arquivo numa janela nova — antes era bloqueada e o download nunca vinha.
  // Agora a janela nova abre escondida (mesma sessão), o download é capturado e ela fecha sozinha.
  _win.webContents.setWindowOpenHandler(({ url }) => {
    _log(`o site abriu uma janela nova: ${String(url).slice(0, 120)}`);
    return { action: 'allow', overrideBrowserWindowOptions: { show: false, webPreferences: { partition: PARTICAO(emp.cnpj), contextIsolation: true, nodeIntegration: false, sandbox: true } } };
  });
  const forca = (wc) => { try { const u = wc.getURL(); if (_arqUrls.has(u) && !_baixando) { _arqUrls.delete(u); _log('o site abriu o arquivo na tela: baixando'); wc.downloadURL(u); } } catch (_) {} };
  _win.webContents.on('did-finish-load', () => forca(_win.webContents));
  _win.webContents.on('did-create-window', (filha) => { _filhas.add(filha); filha.webContents.on('did-finish-load', () => forca(filha.webContents)); filha.on('closed', () => _filhas.delete(filha)); setTimeout(() => { try { if (!filha.isDestroyed()) filha.close(); } catch (_) {} }, 120000); });
  _win.webContents.on('did-navigate', (_e, url) => _log(`abriu ${String(url).split('?')[0]}`));
  _win.webContents.on('did-fail-load', (_e, cod, desc, url) => { if (cod !== -3) _log(`falha ao abrir ${String(url).split('?')[0]}: ${desc} (${cod})`); });
  _win.on('closed', () => { _win = null; _filhas.forEach((f) => { try { f.close(); } catch (_) {} }); if (_espera) { const w = _espera; _espera = null; w({ state: 'fechada' }); } });
  const ses = session.fromPartition(PARTICAO(emp.cnpj));
  if (!_sessoes.has(ses)) {
    _sessoes.add(ses);
    ses.on('will-download', (_ev, item) => {
      const dest = path.join(os.tmpdir(), `fc_dfe_${Date.now()}_${item.getFilename().replace(/[^\w.-]+/g, '_')}`);
      item.setSavePath(dest);
      _log(`download começou: ${item.getFilename()} (${Math.round((item.getTotalBytes() || 0) / 1024)} KB) · ${String(item.getURL()).slice(0, 100)}`);
      _baixando = { nome: item.getFilename(), rec: 0, total: item.getTotalBytes() || 0 };
      item.on('updated', () => { if (_baixando) { _baixando.rec = item.getReceivedBytes(); _baixando.total = item.getTotalBytes() || _baixando.total; } });
      item.once('done', (_e, state) => {
        _baixando = null;
        _log(`download ${state}: ${item.getFilename()}`);
        _filhas.forEach((f) => { try { f.close(); } catch (_) {} });
        if (_espera) { const w = _espera; _espera = null; w({ state, dest, nome: item.getFilename() }); }
      });
    });
    // para ajustar ao site real: registra as respostas que trazem arquivo (tipo e nome), sem gravar conteúdo
    ses.webRequest.onHeadersReceived((det, cb) => {
      try {
        const h = det.responseHeaders || {};
        const ct = String((h['content-type'] || h['Content-Type'] || [''])[0]);
        const cd = String((h['content-disposition'] || h['Content-Disposition'] || [''])[0]);
        if (cd || /zip|octet|xml|pdf/i.test(ct)) {
          _log(`resposta ${det.statusCode} ${ct} ${cd} · ${String(det.url).split('?')[0].slice(0, 100)}`);
          if (det.statusCode === 200 && /zip|octet|xml/i.test(ct) && !/attachment/i.test(cd) && /mainFrame|subFrame/.test(det.resourceType || '')) _arqUrls.set(det.url, Date.now());
        }
      } catch (_) {}
      cb({ responseHeaders: det.responseHeaders });
    });
  }
  return _win;
}
// guarda a referência das imagens que a página recebeu: se a imagem do código não puder ser copiada da página,
// lê exatamente os bytes que a SEFIN mandou (sem pedir outra imagem, que trocaria o código)
const _imgs = new Map();
function _ligaImagens(wc) {
  _imgs.clear();
  try {
    wc.debugger.attach('1.3');
    wc.debugger.on('message', (_e, metodo, p) => {
      if (metodo === 'Network.responseReceived' && p && p.response && (p.type === 'Image' || /^image\//.test(p.response.mimeType || ''))) {
        _imgs.set(p.response.url, p.requestId);
        if (_imgs.size > 80) _imgs.delete(_imgs.keys().next().value);
      }
    });
    wc.debugger.sendCommand('Network.enable').catch(() => {});
  } catch (e) { _log(`leitor de imagens indisponível: ${e.message || e}`); }
}
async function _bytesImagem(src) {
  try {
    if (!src || !_vivo()) return '';
    let id = _imgs.get(src);
    if (!id) { const base = src.split('#')[0]; for (const [u, r] of _imgs) if (u.split('#')[0] === base) id = r; }
    if (!id) return '';
    const r = await _win.webContents.debugger.sendCommand('Network.getResponseBody', { requestId: id });
    if (!r || !r.body) return '';
    const b64 = r.base64Encoded ? r.body : Buffer.from(r.body, 'binary').toString('base64');
    const tipo = /\.jpe?g/i.test(src) ? 'image/jpeg' : /\.gif/i.test(src) ? 'image/gif' : 'image/png';
    return `data:${tipo};base64,${b64}`;
  } catch (_) { return ''; }
}
function _mostra(sim) { try { if (_vivo()) { if (sim) { _win.show(); _win.focus(); } else _win.hide(); } } catch (_) {} }
function _vivo() { return _win && !_win.isDestroyed(); }
async function _vai(url, limite = 45000) {
  if (!_vivo()) throw new Error('janela fechada');
  let venceu = false;
  const t = new Promise((r) => setTimeout(() => { venceu = true; r(); }, limite));
  await Promise.race([_win.loadURL(url).catch((e) => { if (!/ERR_ABORTED/.test(String(e))) _log(`loadURL: ${e.message || e}`); }), t]);
  if (venceu) { _log(`demorou mais de ${limite / 1000}s: ${url}`); try { _win.webContents.stop(); } catch (_) {} }
  await _sleep(800);
}
const _js = (code) => {
  if (!_vivo()) return Promise.reject(new Error('janela fechada'));
  return Promise.race([_win.webContents.executeJavaScript(code, true), new Promise((_r, rej) => setTimeout(() => rej(new Error('a página não respondeu')), 20000))]);
};
async function _print() { try { if (_vivo()) fs.writeFileSync(path.join(D.userData(), 'dfe_ro_ultima.png'), (await _win.webContents.capturePage()).toPNG()); } catch (_) {} }

// ------------------------------------------------------------------ scripts da página
const JS_BASE = `const vis = (e) => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const norm = (s) => String(s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase().replace(/\\s+/g, ' ').trim();
  const clicaveis = () => [...document.querySelectorAll('a, button, li, [role=tab], [role=button], .nav-link, input[type=submit], input[type=button], span')].filter(vis);`;

const JS_ESTADO = `(() => { ${JS_BASE}
  const txt = document.body ? document.body.innerText : '';
  const els = clicaveis();
  const aba = els.find((e) => /CERT\\.?\\s*DIGITAL/.test(norm(e.innerText || e.value)));
  const entrar = els.find((e) => /^ENTRAR$/.test(norm(e.innerText || e.value)) && !e.disabled);
  const acessar = els.find((e) => /^ACESSAR$/.test(norm(e.innerText || e.value)));
  const tab = [...document.querySelectorAll('table')].find((t) => /DOCUMENTO/.test(norm(t.innerText)) && /ESTADO/.test(norm(t.innerText)));
  const nova = els.find((e) => /NOVA SOLICITACAO/.test(norm(e.innerText)));
  const captcha = !!document.querySelector('iframe[src*="captcha"], .g-recaptcha, .h-captcha, [data-sitekey]');
  return { url: location.href, host: location.host, temAba: !!aba, abaAtiva: !!(aba && /active|selected/.test(aba.className + ' ' + (aba.parentElement || {}).className)),
    temEntrar: !!entrar, temAcessar: !!acessar, temTabela: !!tab, temNova: !!nova, captcha,
    cnpjs: [...new Set((txt.match(/\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}/g) || []).map((x) => x.replace(/\\D/g, '')))],
    texto: txt.replace(/\\s+/g, ' ').slice(0, 300) };
})()`;
const JS_CLICA = (re) => `(() => { ${JS_BASE}
  const el = clicaveis().find((e) => ${re}.test(norm(e.innerText || e.value)) && !e.disabled);
  if (el) { el.click(); return true; } return false; })()`;

const JS_LISTA = `(() => { ${JS_BASE}
  const t = [...document.querySelectorAll('table')].find((t) => /DOCUMENTO/.test(norm(t.innerText)) && /ESTADO/.test(norm(t.innerText)));
  if (!t) return { ok: false };
  const trs = [...t.querySelectorAll('tr')];
  const hi = trs.findIndex((tr) => /DOCUMENTO/.test(norm(tr.innerText)) && /ESTADO/.test(norm(tr.innerText)));
  const cab = [...trs[hi].querySelectorAll('th, td')].map((c) => norm(c.innerText));
  const col = (re) => cab.findIndex((c) => re.test(c));
  const ic = col(/CNPJ/), id = col(/^DATA/), idoc = col(/DOCUMENTO/), ies = col(/ESTADO/);
  const rows = trs.slice(hi + 1).map((tr, i) => {
    const td = [...tr.querySelectorAll('td')];
    if (td.length < 4) return null;
    const v = (k) => k >= 0 && td[k] ? td[k].innerText.replace(/\\s+/g, ' ').trim() : '';
    return { i, cnpj: v(ic).replace(/\\D/g, ''), data: v(id), doc: norm(v(idoc)).replace(/[^A-Z]/g, ''), estado: norm(v(ies)),
      temDet: [...tr.querySelectorAll('a, button')].some((b) => /DETALHES/.test(norm(b.innerText))) };
  }).filter(Boolean);
  return { ok: true, rows };
})()`;
const JS_CLICA_DET = (i) => `(() => { ${JS_BASE}
  const t = [...document.querySelectorAll('table')].find((t) => /DOCUMENTO/.test(norm(t.innerText)) && /ESTADO/.test(norm(t.innerText)));
  if (!t) return false;
  const trs = [...t.querySelectorAll('tr')];
  const hi = trs.findIndex((tr) => /DOCUMENTO/.test(norm(tr.innerText)) && /ESTADO/.test(norm(tr.innerText)));
  const tr = trs.slice(hi + 1).filter((tr) => tr.querySelectorAll('td').length >= 4)[${i}];
  const b = tr && [...tr.querySelectorAll('a, button')].find((b) => /DETALHES/.test(norm(b.innerText)));
  if (b) { b.click(); return true; } return false; })()`;

const JS_DETALHES = `(() => { ${JS_BASE}
  const kv = {};
  document.querySelectorAll('tr').forEach((tr) => {
    const c = [...tr.querySelectorAll('th, td')];
    if (c.length >= 2) { const k = norm(c[0].innerText).replace(/:$/, ''); if (k && k.length < 40) kv[k] = c[1].innerText.replace(/\\s+/g, ' ').trim(); }
  });
  const arquivos = [...document.querySelectorAll('a, button')].filter(vis).filter((b) => /(ARQUIVO|PARTE)\\s*\\d+/.test(norm(b.innerText)))
    .map((b, k) => ({ k, texto: b.innerText.replace(/\\s+/g, ' ').trim() }));
  return { ok: !!(kv['PERIODO'] || kv['TIPO DE DOCUMENTO']), kv, arquivos, url: location.href };
})()`;
const JS_CLICA_ARQ = (k, texto) => `(() => { ${JS_BASE}
  const todos = [...document.querySelectorAll('a, button')].filter(vis).filter((b) => /(ARQUIVO|PARTE)\\s*\\d+/.test(norm(b.innerText)));
  const alvo = ${JSON.stringify(texto || '')} ? norm(${JSON.stringify(texto || '')}) : '';
  const b = (alvo && todos.find((b) => norm(b.innerText) === alvo)) || todos[${k}];
  if (b) { b.click(); return true; } return false; })()`;

const JS_AVISO = (txt) => `(() => {
  let d = document.getElementById('fcDfeAviso');
  if (!d) { d = document.createElement('div'); d.id = 'fcDfeAviso';
    d.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:2147483647;background:#1f2a5a;color:#fff;font:600 14px Segoe UI,Arial;padding:10px 16px;text-align:center;box-shadow:0 4px 14px rgba(0,0,0,.25)';
    document.body.appendChild(d); }
  d.textContent = ${JSON.stringify('FiscoCont+: ' + txt)};
})()`;

// Código da imagem (captcha) da SEFIN: acha o quadro "Resolva o texto de verificação", a imagem, a resposta e o ENVIAR.
// O sistema NÃO resolve o código: mostra a imagem para a pessoa digitar e só preenche o que ela digitou.
// O quadro é o menor bloco que tem o título, a imagem, o campo e o botão ENVIAR (no site real o botão pode ficar
// fora do bloco do campo, por isso sobe até achar os quatro).
const JS_CAP_BASE = `${JS_BASE}
  const ehEnviar = (x) => /^ENVIAR$/.test(norm(x.innerText || x.value));
  const quadro = () => {
    const tit = [...document.querySelectorAll('body *')].filter(vis).filter((d) => d.children.length < 4 && /RESOLVA O TEXTO|TEXTO DE VERIFICACAO/.test(norm(d.innerText)) && norm(d.innerText).length < 80);
    for (const t of tit) {
      let el = t;
      for (let k = 0; k < 12 && el && el !== document.body; k++, el = el.parentElement) {
        const img = [...el.querySelectorAll('img, canvas')].filter(vis);
        const inp = [...el.querySelectorAll('input, textarea')].filter(vis).filter((i) => !/hidden|checkbox|radio|submit|button/.test(i.type));
        const bt = [...el.querySelectorAll('button, input[type=submit], input[type=button], a, [role=button]')].filter(vis).filter(ehEnviar);
        if (img.length && inp.length && bt.length) return { box: el, img: img.sort((a, b) => (b.offsetWidth * b.offsetHeight) - (a.offsetWidth * a.offsetHeight))[0], inp: inp[0], bt: bt[0] };
      }
    }
    return null;
  };
  // mensagem que a SEFIN mostra (no quadro ou em aviso solto na página), do jeito que está escrita
  const FIXO = /^(RESOLVA O TEXTO DE VERIFICACAO|TEXTO DE VERIFICACAO|RESPOSTA\\*?:?|FECHAR|ENVIAR|CANCELAR|X|×|CLOSE)$/;
  const mensagem = (q) => {
    const linhas = [];
    if (q) {                                                   // textos do quadro, fora botões, título, rótulos e campo
      const w = document.createTreeWalker(q.box, NodeFilter.SHOW_TEXT);
      for (let nd = w.nextNode(); nd; nd = w.nextNode()) {
        const pai = nd.parentElement, t = String(nd.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!t || !pai || !vis(pai) || pai.closest('button, a, label, h1, h2, h3, h4, script, style, [role=button], .mat-dialog-title, mat-label, option')) continue;
        if (FIXO.test(norm(t)) || t.length > 300 || linhas.includes(t)) continue;
        linhas.push(t);
      }
    }
    [...document.querySelectorAll('[role=alert], .alert, .toast, .toast-message, .snackbar, mat-snack-bar-container, .mat-snack-bar-container, .swal2-popup, .notification, .error, .erro, .invalid-feedback, .mat-error, mat-error, .text-danger')]
      .filter(vis).filter((x) => !q || !q.box.contains(x)).forEach((x) => { const t = String(x.innerText || '').trim(); if (t && t.length < 300 && !linhas.includes(t)) linhas.push(t); });
    return linhas.join(' · ');
  };`;
const JS_CAPTCHA = `(() => { ${JS_CAP_BASE}
  const q = quadro();
  if (!q) return { achou: false, msg: mensagem(null) };
  const el = q.img;
  if (el.tagName === 'IMG' && !(el.complete && el.naturalWidth)) return { achou: true, pronto: false };
  let img = '', tranca = false;
  try {
    if (el.tagName === 'CANVAS') img = el.toDataURL('image/png');
    else if (/^data:image/.test(el.src)) img = el.src;
    else { const c = document.createElement('canvas'); c.width = el.naturalWidth; c.height = el.naturalHeight; c.getContext('2d').drawImage(el, 0, 0); img = c.toDataURL('image/png'); }
  } catch (_) { img = ''; tranca = true; }
  const src = el.tagName === 'IMG' ? el.currentSrc || el.src : '';
  return { achou: true, pronto: true, img, tranca, src: /^data:/.test(src) ? '' : src, chave: (src.length > 300 ? src.slice(-120) : src) + '|' + img.length + '|' + img.slice(-60), msg: mensagem(q) };
})()`;
// como é o quadro (para o "Passo a passo"): nomes de campos e botões, sem a imagem
const JS_CAPTCHA_RAIO_X = `(() => { ${JS_CAP_BASE}
  const q = quadro(); if (!q) return 'quadro do código não encontrado';
  const d = (x) => x ? x.tagName.toLowerCase() + (x.id ? '#' + x.id : '') + (x.name ? '[name=' + x.name + ']' : '') + (typeof x.className === 'string' && x.className ? '.' + x.className.trim().split(/\\s+/).slice(0, 3).join('.') : '') : '-';
  return 'quadro ' + d(q.box) + ' · imagem ' + d(q.img) + ' ' + String(q.img.src || '').split('?')[0].slice(0, 80) + ' · campo ' + d(q.inp) + ' maxlength=' + (q.inp.maxLength || '') + ' · botão ' + d(q.bt) + (q.bt.disabled ? ' (desabilitado)' : '') + ' · form=' + !!q.inp.form;
})()`;
const JS_CAPTCHA_ENVIA = (texto) => `(async () => { ${JS_CAP_BASE}
  const q = quadro();
  if (!q) return { ok: false, motivo: 'quadro do código sumiu' };
  const inp = q.inp, v = ${JSON.stringify(String(texto || ''))};
  inp.focus();
  const proto = inp.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(inp, v);
  inp.dispatchEvent(new InputEvent('input', { bubbles: true, data: v, inputType: 'insertText' }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: v.slice(-1) }));
  inp.dispatchEvent(new Event('blur', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 350));                 // o site habilita o ENVIAR depois de ler o campo
  const b = quadro() ? quadro().bt : q.bt;
  if (inp.value !== v) return { ok: false, motivo: 'o campo não ficou com o código digitado' };
  if (b.disabled) return { ok: false, motivo: 'o botão ENVIAR continuou desabilitado' };
  b.click();
  return { ok: true };
})()`;
const JS_LINK_BAIXAR = `(() => { ${JS_BASE}
  const b = [...document.querySelectorAll('a, button')].filter(vis).find((x) => /^(BAIXAR|DOWNLOAD|CLIQUE AQUI)/.test(norm(x.innerText)) && !/DETALHES|COMPROVANTE/.test(norm(x.innerText)));
  if (b) { b.click(); return true; } return false; })()`;

// Nova Solicitação: preenche o que reconhecer (Período, documento, operação Emitida, datas). A pessoa confere e confirma.
const JS_NOVA = (doc, ini, fim, iniIso, fimIso) => `(() => { ${JS_BASE}
  const set = (el, v) => { const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value'); d.set.call(el, v);
    ['input', 'change', 'blur'].forEach((t) => el.dispatchEvent(new Event(t, { bubbles: true }))); };
  const feito = {};
  const rotulo = (inp) => norm((inp.labels && inp.labels[0] && inp.labels[0].innerText) || (inp.parentElement && inp.parentElement.innerText) || inp.value);
  const rad = [...document.querySelectorAll('input[type=radio]')];
  const per = rad.find((r) => /PERIODO/.test(rotulo(r)));
  if (per && !per.checked) per.click();
  feito.periodo = !!per;
  const sels = [...document.querySelectorAll('select')].filter(vis);
  const sd = sels.find((s) => [...s.options].some((o) => /^CTE$/.test(norm(o.text).replace(/[^A-Z]/g, ''))));
  if (sd) { const o = [...sd.options].find((o) => norm(o.text).replace(/[^A-Z]/g, '') === '${doc}');
    if (o) { sd.value = o.value; ['input', 'change'].forEach((t) => sd.dispatchEvent(new Event(t, { bubbles: true }))); feito.doc = o.text; } }
  const opRad = rad.find((r) => /^EMITIDA$/.test(rotulo(r)));
  if (opRad && !opRad.checked) { opRad.click(); feito.op = 'radio'; }
  const so = sels.find((s) => [...s.options].some((o) => /EMITIDA/.test(norm(o.text))));
  if (so) { const o = [...so.options].find((o) => /^EMITIDAS?$/.test(norm(o.text))); if (o) { so.value = o.value; so.dispatchEvent(new Event('change', { bubbles: true })); feito.op = o.text; } }
  const datas = [...document.querySelectorAll('input')].filter(vis).filter((i) => i.type === 'date' || /DATA|INICI|FINAL|FIM|PERIODO|ATE/.test(norm(i.placeholder + ' ' + i.name + ' ' + i.id + ' ' + rotulo(i))) && !/CHAVE|NUMERO|NNF/.test(norm(i.name + i.id)));
  if (datas.length >= 2) {
    set(datas[0], datas[0].type === 'date' ? '${iniIso}' : '${ini}'); set(datas[1], datas[1].type === 'date' ? '${fimIso}' : '${fim}'); feito.datas = true;
  }
  return feito;
})()`;

// ------------------------------------------------------------------ passos
function _norm(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase(); }
function _isoDe(dataBr) { const m = String(dataBr || '').match(/(\d{2})\/(\d{2})\/(\d{4})/); return m ? `${m[3]}-${m[2]}-${m[1]}` : ''; }
function _periodoDe(comp) {
  const [a, m] = comp.split('-').map(Number);
  const ult = new Date(a, m, 0).getDate();
  const mm = String(m).padStart(2, '0');
  return { ini: `01/${mm}/${a}`, fim: `${ult}/${mm}/${a}`, iniIso: `${a}-${mm}-01`, fimIso: `${a}-${mm}-${ult}` };
}

async function _login(emp) {
  _prog(`${emp.nome}: entrando no DFe-Download com o certificado da empresa…`);
  await _vai(`${BASE}/solicitacoes`, 60000);
  const ate = Date.now() + 120000;
  let entrou = 0, aba = 0, acessar = 0, ultimo = '';
  while (Date.now() < ate) {
    if (_certFaltou) throw new Error('o certificado (e-CNPJ) da empresa não está instalado no Windows. Instale o certificado e tente de novo.');
    const st = await _js(JS_ESTADO).catch(() => null);
    if (st) {
      if (st.texto !== ultimo) { _log(`tela: ${st.host} · ${st.texto}`); ultimo = st.texto; }
      if (st.host === HOST && (st.temTabela || st.temNova)) {
        const outro = st.cnpjs.find((c) => c !== emp.cnpj);
        if (st.cnpjs.length && !st.cnpjs.includes(emp.cnpj) && outro) throw new Error(`o site entrou com outro CNPJ (${_fmtCnpj(outro)}). Nada foi baixado.`);
        return true;
      }
      if (st.host !== HOST) {                                   // SSO da SEFIN
        if (st.captcha) throw new Error('o acesso pediu captcha antes do login. Entre uma vez pelo navegador e tente de novo.');
        if (st.temEntrar && entrou < 3) {
          const outro = st.cnpjs.find((c) => c !== emp.cnpj);
          if (st.cnpjs.length && !st.cnpjs.includes(emp.cnpj)) throw new Error(`o acesso mostrou outro CNPJ (${_fmtCnpj(outro)}). Nada foi baixado.`);
          await _js(JS_CLICA('/^ENTRAR$/')); entrou++; _log('clicou em Entrar'); await _sleep(2000); continue;
        }
        if (st.temAba && aba < 2) { await _js(JS_CLICA('/CERT\\.?\\s*DIGITAL/')); aba++; _log('abriu a aba do certificado digital'); await _sleep(2500); continue; }
      } else if (st.temAcessar && acessar < 3) {
        await _js(JS_CLICA('/^ACESSAR$/')); acessar++; _log('clicou em Acessar'); await _sleep(2000); continue;
      }
    }
    await _sleep(1500);
  }
  await _print();
  throw new Error('não consegui entrar no DFe-Download. Veja o print em "dfe_ro_ultima.png" e o passo a passo em "dfe_ro_log.txt" (pasta de dados do FiscoCont+).');
}

async function _lista() {
  for (let t = 0; t < 3; t++) {
    const st = await _js(JS_ESTADO).catch(() => null);
    if (!st || st.host !== HOST || !st.temTabela) { await _vai(`${BASE}/solicitacoes`); await _sleep(1500); }
    const r = await _js(JS_LISTA).catch(() => null);
    if (r && r.ok) return r.rows;
    await _sleep(2000);
  }
  await _print();
  throw new Error('não achei a lista "Ver Solicitações".');
}

async function _detalhes(i) {
  await _js(JS_CLICA_DET(i));
  for (let t = 0; t < 15; t++) {
    await _sleep(1000);
    const d = await _js(JS_DETALHES).catch(() => null);
    if (d && d.ok) return d;
  }
  return null;
}

function _confere(det, comp) {
  const kv = det.kv;
  const per = _periodoDe(comp);
  const periodo = (kv['PERIODO'] || '').replace(/\s+/g, ' ');
  const datas = periodo.match(/\d{2}\/\d{2}\/\d{4}/g) || [];
  const okPer = datas.length === 2 && datas[0] === per.ini && datas[1] === per.fim;
  const okTipo = /PERIODO/.test(_norm(kv['TIPO DE PESQUISA']));
  const okOp = /EMITIDA/.test(_norm(kv['TIPO DE OPERACAO']));
  const okSit = !kv['SITUACAO'] || /ATIVO/.test(_norm(kv['SITUACAO']));
  const exp = _isoDe(kv['DATA DE EXPIRACAO']);
  const expirado = !!exp && exp < new Date().toISOString().slice(0, 10);
  return { ok: okPer && okTipo && okOp && okSit, expirado, id: kv['IDENTIFICACAO'] || '', canc: /CANCEL/.test(_norm(kv['SITUACAO'])) };
}

function _esperaDownload(limiteMs) {
  return new Promise((resolve) => {
    const t = setTimeout(() => { if (_espera) { _espera = null; resolve({ state: 'tempo' }); } }, limiteMs);
    _espera = (r) => { clearTimeout(t); resolve(r); };
  });
}

// pede o código à pessoa numa janela do FiscoCont+ (renderer) e espera a resposta (null = cancelou)
function _pedirCodigo(dados) {
  return new Promise((resolve) => {
    const id = ++_capSeq;
    const t = setTimeout(() => { if (_capPend && _capPend.id === id) { _capPend = null; resolve(null); } }, 10 * 60 * 1000);
    _capPend = { id, resolve: (v) => { clearTimeout(t); resolve(v); } };
    try { D.notificar('dfe:captcha', { id, ...dados }); } catch (_) { clearTimeout(t); _capPend = null; resolve(null); }
  });
}
function respostaCodigo(id, texto) {
  if (!_capPend || _capPend.id !== id) return { ok: false };
  const p = _capPend; _capPend = null; p.resolve(texto == null ? null : String(texto).trim());
  return { ok: true };
}
async function _imagemCodigo(c) {
  if (c.img && c.img.length > 200) return { img: c.img, como: 'cópia da página' };
  const b = await _bytesImagem(c.src);
  if (b) return { img: b, como: 'arquivo recebido da SEFIN' };
  return { img: '', como: c.tranca ? 'imagem protegida' : 'sem imagem' };
}
// espera o quadro do código ficar pronto (imagem carregada); devolve null se não aparecer em `ms`
async function _esperaQuadro(espera, ms) {
  const fim = Date.now() + ms;
  while (Date.now() < fim) {
    const r = await Promise.race([espera.then((x) => ({ fim: x })), _sleep(500).then(() => null)]);
    if (r && r.fim) return { fim: r.fim };
    const c = await _js(JS_CAPTCHA).catch(() => null);
    if (c && c.achou && c.pronto) return { c };
  }
  return null;
}

// baixa UM arquivo (parte) do pedido: clica, mostra o código no FiscoCont+, envia o que a pessoa digitou, espera o download
async function _baixarParte(emp, tipo, achado, a, n, tot) {
  const k = achado.det.arquivos.findIndex((x) => x.texto === a.texto);
  const espera = _esperaDownload(20 * 60 * 1000);
  const clicou = await _js(JS_CLICA_ARQ(k, a.texto)).catch(() => false);
  if (!clicou) { _log(`não achei o link "${a.texto}" na tela de Detalhes`); await _print(); return { state: 'sem_link' }; }
  let msgSefin = '', aviso = '', raioX = false;
  for (let tent = 1; tent <= 6; tent++) {
    const q = await _esperaQuadro(espera, 12000);
    if (q && q.fim) return q.fim;
    if (!q) {
      if (await _js(JS_LINK_BAIXAR).catch(() => false)) { _log('clicou no link de baixar que apareceu'); const r = await Promise.race([espera, _sleep(30000).then(() => null)]); if (r) return r; }
      const m = await _js(JS_CAPTCHA).catch(() => null);
      if (m && m.msg) _log(`mensagem da SEFIN: ${m.msg}`);
      await _print();
      _log('o código da imagem não apareceu e o download não começou');
      return { state: 'sem_codigo', msg: m && m.msg };
    }
    const c = q.c;
    if (!raioX) { raioX = true; _log(`código: ${await _js(JS_CAPTCHA_RAIO_X).catch((e) => String(e.message || e))}`); }
    if (c.msg && tent === 1) msgSefin = c.msg;
    const im = await _imagemCodigo(c);
    _log(`imagem do código: ${im.como}`);
    if (!im.img) {                                          // não deu para trazer a imagem: mostra a página da SEFIN
      _log('não consegui trazer a imagem do código: mostrando a página da SEFIN');
      _mostra(true);
      await _js(JS_AVISO(`digite o código da imagem e clique em ENVIAR (${NOME[tipo]}, parte ${n} de ${tot}).`)).catch(() => {});
      _prog(`${emp.nome} · ${NOME[tipo]}: digite o código na janela da SEFIN (parte ${n} de ${tot})…`, { espera: true });
      const r = await espera; _mostra(false); return r;
    }
    _prog(`${emp.nome} · ${NOME[tipo]}: digite o código da imagem (parte ${n} de ${tot})…`, { espera: true });
    const texto = await _pedirCodigo({ empresa: emp.nome, doc: NOME[tipo], parte: n, partes: tot, img: im.img, msgSefin, aviso });
    if (texto == null) return { state: 'cancelado' };
    // confere se o código pedido ainda é o mesmo da imagem mostrada (se a SEFIN trocou, mostra a nova)
    const agora = await _js(JS_CAPTCHA).catch(() => null);
    if (agora && agora.achou && agora.pronto && agora.chave !== c.chave) { _log('a SEFIN trocou a imagem antes do envio: mostra a nova'); msgSefin = agora.msg || ''; aviso = 'A imagem foi trocada pela SEFIN. Digite o código desta nova imagem.'; continue; }
    const env = await _js(JS_CAPTCHA_ENVIA(texto)).catch((e) => ({ ok: false, motivo: String(e.message || e) }));
    _log(`código enviado (tentativa ${tent}): ${env.ok ? 'ENVIAR clicado' : 'não enviado: ' + env.motivo}`);
    if (!env.ok) { await _print(); msgSefin = ''; aviso = `O FiscoCont+ não conseguiu enviar o código (${env.motivo}). Digite de novo.`; continue; }
    _prog(`${emp.nome} · ${NOME[tipo]}: baixando a parte ${n} de ${tot}…`);
    // depois do ENVIAR: ou vem o arquivo, ou a SEFIN mostra uma mensagem/imagem nova
    msgSefin = ''; aviso = '';
    let volta = false;
    const limite = Date.now() + 15 * 60 * 1000;
    for (let t = 0; t < 180 && !volta; t++) {
      const r = await Promise.race([espera.then((x) => ({ fim: x })), _sleep(1000).then(() => null)]);
      if (r && r.fim) return r.fim;
      if (_baixando) {                                       // o arquivo está chegando: espera terminar (até 15 min)
        const b = _baixando, mb = (x) => (x / 1048576).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
        _prog(`${emp.nome} · ${NOME[tipo]}: recebendo a parte ${n} de ${tot}${b.total ? ` · ${mb(b.rec)} de ${mb(b.total)} MB` : b.rec ? ` · ${mb(b.rec)} MB` : ''}…`);
        if (Date.now() < limite) t--;
        continue;
      }
      if (t === 30) _prog(`${emp.nome} · ${NOME[tipo]}: a SEFIN está preparando o arquivo (parte ${n} de ${tot})…`);
      if (t < 2) continue;
      const cc = await _js(JS_CAPTCHA).catch(() => null);
      if (!cc) continue;
      if (cc.msg && cc.msg !== c.msg) { msgSefin = cc.msg; _log(`mensagem da SEFIN: ${cc.msg}`); }
      if (cc.achou && cc.pronto && (cc.chave !== c.chave || (cc.msg && cc.msg !== c.msg))) { volta = true; break; }
      if (cc.achou && t === 25) { _log('o quadro do código continua aberto, sem mensagem e sem arquivo'); await _print(); aviso = 'A SEFIN não respondeu ao código. Digite de novo.'; volta = true; break; }
      if (!cc.achou && (t === 15 || t === 60 || t === 120) && await _js(JS_LINK_BAIXAR).catch(() => false)) _log('clicou no link de baixar que apareceu');
    }
    if (!volta) { await _print(); _log('o arquivo não chegou em 3 min depois do código'); return { state: 'tempo', msg: msgSefin }; }
    _log('o código voltou: pede de novo');
  }
  return { state: 'tempo', msg: msgSefin };
}

// antes da próxima parte: continua na tela de Detalhes se ela ainda estiver aberta; se não, volta pela lista
async function _voltaDetalhes(achado, a) {
  for (let t = 0; t < 4; t++) {
    const d = await _js(JS_DETALHES).catch(() => null);
    if (d && d.ok && d.arquivos.some((x) => x.texto === a.texto)) return true;
    await _sleep(800);
  }
  _log('voltando aos Detalhes do pedido pela lista de solicitações');
  await _vai(`${BASE}/solicitacoes`);
  await _sleep(1500);
  const rows = await _lista().catch(() => []);
  const row = rows.find((r) => r.data === achado.row.data && r.doc === achado.row.doc) || rows[achado.row.i];
  if (row) {
    const d = await _detalhes(row.i);
    if (d && d.arquivos.some((x) => x.texto === a.texto)) return true;
  }
  if (achado.det.url && !/\/solicitacoes\/?$/.test(achado.det.url)) {
    await _vai(achado.det.url); await _sleep(1500);
    const d = await _js(JS_DETALHES).catch(() => null);
    if (d && d.ok && d.arquivos.some((x) => x.texto === a.texto)) return true;
  }
  return false;
}

async function _baixar(emp, tipo, comp, achado, est, pasta) {
  const feitos = est.arquivos || [];
  const todos = achado.det.arquivos;
  if (!todos.length) return { status: 'erro', msg: 'o pedido está liberado, mas não achei o link do arquivo nos Detalhes.' };
  const arqs = todos.filter((a) => !feitos.includes(`${achado.conf.id}|${a.texto}`));
  if (!arqs.length) return { ...est, status: 'baixado', msg: 'já baixado antes' };
  _log(`${NOME[tipo]}: ${todos.length} arquivo(s)/parte(s) no pedido: ${todos.map((a) => a.texto).join(' | ')}`);
  const baixados = [];
  let motivo = '', estMotivo = '';
  for (const [n, a] of arqs.entries()) {
    if (!_vivo()) return { status: 'cancelado', msg: 'a busca foi interrompida.' };
    if (n > 0) { _prog(`${emp.nome} · ${NOME[tipo]}: indo para a parte ${n + 1} de ${arqs.length}…`); await _sleep(1500); await _voltaDetalhes(achado, a); }
    const r = await _baixarParte(emp, tipo, achado, a, n + 1, arqs.length);
    if (r.state !== 'completed') {
      motivo = r.msg ? `a SEFIN respondeu: ${r.msg}` : { cancelado: 'o código não foi digitado (pulado).', fechada: 'a busca foi interrompida.', tempo: 'o arquivo não chegou depois do código.',
        sem_codigo: 'o site não mostrou o código nem o arquivo.', sem_link: `não achei o link "${a.texto}" nos Detalhes.` }[r.state] || `download ${r.state}`;
      estMotivo = r.state;
      _log(`${a.texto}: ${motivo}`);
      if (baixados.length) break;                           // extrai o que já veio; o resto fica para a próxima
      return { status: r.state === 'cancelado' ? 'aguardando_codigo' : 'erro', msg: motivo + (r.state === 'cancelado' ? '' : ' Veja o "Passo a passo".') };
    }
    baixados.push({ dest: r.dest, chave: `${achado.conf.id}|${a.texto}` });
  }
  // todas as partes juntas: arquivo dividido em partes também é juntado antes de abrir
  const out = path.join(os.tmpdir(), `fc_dfe_x_${Date.now()}.json`);
  const args = ['dfe-extrair', '--pasta', pasta, '--empresa', emp.nome, '--cnpj', emp.cnpj, '--tipo', tipo, '--competencia', comp, '--json', out];
  baixados.forEach((b) => args.push('--zip', b.dest));
  await D.runFiscal(args, out);
  const x = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
  baixados.forEach((b) => fs.unlink(b.dest, () => {}));
  if (x.erro) return { status: 'erro', msg: x.erro };
  baixados.forEach((b) => feitos.push(b.chave));
  const falta = todos.length - todos.filter((a) => feitos.includes(`${achado.conf.id}|${a.texto}`)).length;
  _log(`${NOME[tipo]}: ${x.qtd} nota(s) extraídas de ${baixados.length} parte(s) · R$ ${x.valor}`);
  return { status: falta ? 'parcial' : 'baixado', msg: falta ? `${todos.length - falta} de ${todos.length} parte(s) baixada(s). A parte que faltou: ${motivo || 'não baixada'} Clique em Baixar notas de novo para baixar só ela.` : '',
    partes: todos.length, faltam: falta,
    qtd: (est.qtd || 0) + x.qtd, valor: Math.round(((est.valor || 0) + x.valor) * 100) / 100, canceladas: (est.canceladas || 0) + x.canceladas,
    pasta: x.pasta || est.pasta || '', arquivos: feitos, id: achado.conf.id };
}

async function _novaSolicitacao(emp, tipo, comp) {
  const per = _periodoDe(comp);
  await _vai(`${BASE}/solicitacoes`);
  const clicou = await _js(JS_CLICA('/NOVA SOLICITACAO/')).catch(() => false);
  if (!clicou) return { status: 'erro', msg: 'não achei "Nova Solicitação".' };
  await _sleep(2000);
  let f = await _js(JS_NOVA(DOCS[tipo], per.ini, per.fim, per.iniIso, per.fimIso)).catch(() => ({}));
  await _sleep(1200);
  f = { ...f, ...(await _js(JS_NOVA(DOCS[tipo], per.ini, per.fim, per.iniIso, per.fimIso)).catch(() => ({}))) };       // campos que aparecem depois de escolher Período
  _log(`nova solicitação ${NOME[tipo]} preenchida: ${JSON.stringify(f)}`);
  _mostra(true);                                            // a pessoa confere e confirma o pedido na página da SEFIN
  await _js(JS_AVISO(`confira o pedido (Período ${per.ini} a ${per.fim} · ${NOME[tipo]} · Emitida, ativas e canceladas) e confirme no botão do site. Depois a SEFIN prepara o arquivo.`)).catch(() => {});
  _prog(`${emp.nome} · ${NOME[tipo]}: confira e confirme a Nova Solicitação na janela da SEFIN…`, { espera: true });
  const antes = Date.now(), ate = antes + 5 * 60 * 1000;
  while (Date.now() < ate) {
    if (!_vivo()) return { status: 'cancelado', msg: 'a janela foi fechada antes de confirmar o pedido.' };
    const st = await _js(JS_ESTADO).catch(() => null);
    if (st && st.temTabela) {
      const rows = await _js(JS_LISTA).catch(() => ({ rows: [] }));
      const hoje = new Date().toISOString().slice(0, 10);
      if ((rows.rows || []).some((r) => r.doc === DOCS[tipo] && _isoDe(r.data) === hoje)) {
        _log(`pedido ${NOME[tipo]} feito`);
        _mostra(false);
        return { status: 'solicitado', msg: 'pedido feito; a SEFIN prepara o arquivo. Clique em Baixar notas de novo mais tarde.', pedidoEm: new Date().toISOString() };
      }
    }
    await _sleep(2500);
  }
  return { status: 'erro', msg: 'o pedido não foi confirmado em 5 minutos.' };
}

async function _empresa(emp, comp, tipos, pasta, estado) {
  _cnpjAtivo = emp.cnpj; _certFaltou = false;
  const res = {};
  estado[emp.cnpj] = estado[emp.cnpj] || {};
  const est = estado[emp.cnpj][comp] = estado[emp.cnpj][comp] || {};
  try {
    _janela(emp);
    await _login(emp);
    for (const tipo of tipos) {
      if (!_vivo()) { res[tipo] = { status: 'cancelado', msg: 'a janela foi fechada.' }; continue; }
      const anterior = est[tipo] || {};
      _prog(`${emp.nome} · ${NOME[tipo]}: procurando o pedido de ${comp.split('-').reverse().join('/')} em Ver Solicitações…`);
      const rows = await _lista();
      const outro = rows.find((r) => r.cnpj && r.cnpj !== emp.cnpj);
      if (outro) throw new Error(`a lista mostra pedidos de outro CNPJ (${_fmtCnpj(outro.cnpj)}). Nada foi baixado.`);
      // pedidos do tipo feitos a partir do mês; primeiro o já usado antes e os liberados para download (menos telas de Detalhes)
      const cands = rows.filter((r) => r.doc === DOCS[tipo] && r.temDet && (!_isoDe(r.data) || _isoDe(r.data) >= `${comp}-01`))
        .sort((a, b) => ((anterior.data && b.data === anterior.data) - (anterior.data && a.data === anterior.data)) || (/DOWNLOAD/.test(b.estado) - /DOWNLOAD/.test(a.estado)))
        .slice(0, 8);
      let achado = null;
      for (const c of cands) {
        const det = await _detalhes(c.i);
        if (det) {
          const conf = _confere(det, comp);
          _log(`pedido ${c.data} ${c.doc} ${c.estado}: ${JSON.stringify(det.kv)} → ${conf.ok ? 'é o do mês' : 'outro'}`);
          if (conf.ok && !conf.expirado) { achado = { row: c, det, conf }; break; }
        }
        await _vai(`${BASE}/solicitacoes`);
      }
      let r;
      if (achado) anterior.data = achado.row.data;
      if (achado && /DOWNLOAD/.test(achado.row.estado)) {
        r = await _baixar(emp, tipo, comp, achado, anterior, pasta);
      } else if (achado && /NAO ENCONTRAD/.test(_norm(achado.row.estado))) {
        r = { status: 'sem_notas', msg: 'a SEFIN não encontrou nota no período.' };
      } else if (achado) {
        r = { status: 'aguardando', msg: `pedido do mês encontrado (${achado.row.data}); a SEFIN ainda está preparando o arquivo.` };
      } else if (anterior.status === 'solicitado' && anterior.pedidoEm && Date.now() - Date.parse(anterior.pedidoEm) < 6 * 3600 * 1000) {
        r = { ...anterior, status: 'aguardando', msg: 'pedido feito pelo sistema; a SEFIN ainda não liberou.' };
      } else {
        r = await _novaSolicitacao(emp, tipo, comp);
      }
      est[tipo] = { ...anterior, ...r, quando: new Date().toISOString() };
      res[tipo] = est[tipo];
      _gravaEstado(estado);
    }
  } catch (e) {
    _log(`ERRO: ${e.message || e}`);
    await _print();
    for (const t of tipos) if (!res[t]) { res[t] = { status: 'erro', msg: String(e.message || e) }; est[t] = { ...(est[t] || {}), ...res[t], quando: new Date().toISOString() }; }
    _gravaEstado(estado);
  } finally {
    try { if (_vivo()) _win.close(); } catch (_) {}
    _win = null;
  }
  return res;
}

// empresas: [{ cnpj, nome }] já filtradas para RO · tipos: ['nfe','nfce'] · comp: 'AAAA-MM'
async function baixar(empresas, comp, tipos) {
  if (_rodando) throw new Error('Já existe uma busca do DFe-Download em andamento.');
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(comp || '')) throw new Error('Competência inválida.');
  const pasta = D.pastaBase();
  if (!pasta) throw new Error('Escolha a pasta das Baixas DF-e primeiro.');
  _rodando = true; _parar = false; _logTxt = [];
  const estado = lerEstado();
  const saida = [];
  try {
    for (const [n, emp] of empresas.entries()) {
      if (_parar) { saida.push({ cnpj: emp.cnpj, nome: emp.nome, parado: true }); continue; }
      _prog(`Saídas · ${emp.nome} (${n + 1} de ${empresas.length})…`);
      _log(`===== ${emp.nome} (${_fmtCnpj(emp.cnpj)}) · ${comp}`);
      const r = await _empresa(emp, comp, tipos, D.pastaDe ? D.pastaDe(emp, pasta) : pasta, estado);
      saida.push({ cnpj: emp.cnpj, nome: emp.nome, ...r });
    }
  } finally { _rodando = false; _prog(''); }
  return { empresas: saida };
}

function cancelar() { _parar = true; if (_capPend) respostaCodigo(_capPend.id, null); try { if (_vivo()) _win.close(); } catch (_) {} return { ok: true }; }

function gravaEstado(est) { _gravaEstado(est); }

module.exports = { init, baixar, lerEstado, gravaEstado, respostaCodigo, cancelar };
