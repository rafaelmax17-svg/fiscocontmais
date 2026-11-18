'use strict';
// Consulta NF-e por chave · EVENTOS pelo Portal Nacional da NF-e (pedido do Rafael, 18/11/2026).
//
// Quando o serviço da SEFAZ autorizadora devolve a NF-e (modelo 55) autorizada SEM eventos, o sistema busca os eventos no
// Portal Nacional (www.nfe.fazenda.gov.br) — lá aparecem também os registrados no Ambiente Nacional (Ciência, Confirmação,
// Desconhecimento, Operação não Realizada…), que a consulta da SEFAZ autorizadora não traz.
//   1. abre a consulta (resumo) numa janela própria, com a chave já preenchida;
//   2. mostra SÓ o quadro do "Sou humano" (hCaptcha): quem marca é a PESSOA — o sistema nunca resolve captcha;
//   3. depois, escondido: Continuar → Consulta Completa → OK do aviso → certificado da empresa (e-CNPJ instalado no
//      Windows, escolhido pelo CNPJ) → lê a tabela "Eventos da NF-e" (nome, protocolo, data de autorização, inclusão no AN).
// Sem o e-CNPJ da empresa no Windows, nem abre a janela: devolve o aviso. O passo a passo fica em nfe_portal_log.txt e a
// última tela em nfe_portal_ultima.png (pasta de dados), para ajustar ao site real.

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { app, BrowserWindow, session } = require('electron');

const URL_RESUMO = 'https://www.nfe.fazenda.gov.br/portal/consultaRecaptcha.aspx?tipoConsulta=resumo&tipoConteudo=7PhJ+gAVw2g=';
const PARTICAO = (cnpj) => `persist:nfe-portal-${cnpj}`;
const ESPERA_CAPTCHA = 4 * 60000;

let D = null;                    // { userData(), janelaPai() }
let _win = null, _cnpjAtivo = '', _certFaltou = false, _parar = false;
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _so = (s) => String(s || '').replace(/\D/g, '');

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
    _log(`o site pediu certificado (${String(url).split('?')[0]}): ${lista.length} no Windows · ${alvo ? 'usando o e-CNPJ da empresa' : 'e-CNPJ da empresa NÃO instalado'}`);
    event.preventDefault();
    if (!alvo) _certFaltou = true;
    // sem o certificado: null (o Electron recusa undefined com "Must pass valid certificate object" e derruba o sistema)
    callback(alvo || null);
  });
}

let _logTxt = [];
function _log(m) {
  _logTxt.push(`${new Date().toLocaleTimeString('pt-BR')} ${m}`);
  try { fs.writeFileSync(path.join(D.userData(), 'nfe_portal_log.txt'), _logTxt.slice(-500).join('\n')); } catch (_) {}
}
async function _foto() {
  try { if (_vivo()) fs.writeFileSync(path.join(D.userData(), 'nfe_portal_ultima.png'), (await _win.webContents.capturePage()).toPNG()); } catch (_) {}
}
const _vivo = () => _win && !_win.isDestroyed();

// ------------------------------------------------------------------ e-CNPJ instalado no Windows?
let _certs = { em: 0, cnpjs: [] };
function cnpjsInstalados() {
  if (Date.now() - _certs.em < 10 * 60000) return Promise.resolve(_certs.cnpjs);
  return new Promise((resolve) => {
    if (process.platform !== 'win32') { resolve([]); return; }
    const ps = "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) } | ForEach-Object { $_.Subject }";
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true, timeout: 30000 }, (err, out) => {
      const cnpjs = err ? [] : [...new Set((String(out || '').match(/:(\d{14})\b/g) || []).map((x) => x.slice(1)))];
      _certs = { em: Date.now(), cnpjs };
      resolve(cnpjs);
    });
  });
}

// ------------------------------------------------------------------ janela
function _janela(cnpj) {
  if (_vivo() && _cnpjAtivo === cnpj) return _win;
  if (_vivo()) _win.destroy();
  _cnpjAtivo = cnpj;
  const pai = D.janelaPai && D.janelaPai();
  _win = new BrowserWindow({ show: false, width: 480, height: 660, resizable: false, minimizable: false, maximizable: false,
    title: 'FiscoCont+ · Confirme que você é humano', autoHideMenuBar: true, parent: pai && !pai.isDestroyed() ? pai : undefined,
    webPreferences: { partition: PARTICAO(cnpj), contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
  const ses = session.fromPartition(PARTICAO(cnpj));
  try { ses.setUserAgent(ses.getUserAgent().replace(/\s(Electron|fiscocont[\w-]*)\/\S+/gi, '')); } catch (_) {}
  // o aviso "é necessário possuir um certificado digital" é confirmado pelo sistema (OK)
  _win.webContents.on('did-navigate', (_e, url) => _log(`abriu ${String(url).split('?')[0]}`));
  _win.webContents.on('did-fail-load', (_e, cod, desc, url) => { if (cod !== -3) _log(`falha ao abrir ${String(url).split('?')[0]}: ${desc} (${cod})`); });
  _win.webContents.on('dom-ready', () => { _win.webContents.executeJavaScript('window.confirm = () => true; window.alert = () => {};').catch(() => {}); });
  _win.on('close', (ev) => { if (_win && _win.isVisible()) { ev.preventDefault(); _parar = true; _win.hide(); } });
  _win.on('closed', () => { _win = null; });
  return _win;
}
const _js = (code) => (_vivo() ? _win.webContents.executeJavaScript(code, true) : Promise.reject(new Error('janela fechada')));
async function _carregou(ms = 25000) {
  const fim = Date.now() + ms;
  await _sleep(400);
  while (Date.now() < fim) {
    if (!_vivo()) throw new Error('janela fechada');
    if (!_win.webContents.isLoading()) { try { if (await _js('document.readyState') === 'complete') return; } catch (_) {} }
    await _sleep(300);
  }
}
function _mostrar() {
  if (!_vivo()) return;
  const pai = D.janelaPai && D.janelaPai();
  if (pai && !pai.isDestroyed()) {
    const b = pai.getBounds(), [w, h] = _win.getSize();
    _win.setPosition(Math.round(b.x + (b.width - w) / 2), Math.round(b.y + (b.height - h) / 2));
  }
  _win.show(); _win.focus();
}

// Na tela fica só o quadro do "Sou humano" (e o desafio de imagens do hCaptcha, quando ele pedir), com uma faixa do
// FiscoCont+ em cima. Todo o resto da página fica invisível.
const JS_SO_CAPTCHA = (titulo) => `(() => {
  const cap = document.querySelector('.h-captcha, [data-hcaptcha-widget-id], iframe[src*="hcaptcha"]');
  const alvo = cap && (cap.closest('.h-captcha') || cap.parentElement);
  if (!alvo) return false;
  if (!document.getElementById('fcFaixa')) {
    const st = document.createElement('style'); st.id = 'fcEstilo';
    st.textContent = 'html,body{overflow:hidden!important;background:#f3f5fa!important}body *{visibility:hidden!important}'
      + '.fc-alvo,.fc-alvo *,iframe[src*="hcaptcha"],#fcFaixa,#fcFaixa *{visibility:visible!important}'
      + '.fc-alvo{position:fixed!important;top:150px!important;left:50%!important;transform:translateX(-50%)!important;margin:0!important;z-index:2147483000!important}'
      + '#fcFaixa{position:fixed;top:0;left:0;right:0;z-index:2147483001;background:linear-gradient(135deg,#2563eb,#0891b2);color:#fff;padding:16px 18px;font:14px/1.4 "Segoe UI",system-ui,sans-serif}'
      + '#fcFaixa b{display:block;font-size:15px}#fcFaixa span{display:block;opacity:.92;font-size:12.5px;margin-top:4px}'
      + '#fcPular{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:2147483001;border:1.5px solid #dbe1ee;background:#fff;color:#141b2d;border-radius:10px;padding:8px 16px;font:700 12.5px "Segoe UI",system-ui,sans-serif;cursor:pointer;visibility:visible!important}';
    document.head.appendChild(st);
    const f = document.createElement('div'); f.id = 'fcFaixa';
    f.innerHTML = '<b></b><span>Marque “Sou humano”. Depois disso o sistema continua sozinho e fecha esta janela.</span>';
    f.querySelector('b').textContent = ${JSON.stringify(titulo)};
    document.body.appendChild(f);
    const p = document.createElement('button'); p.id = 'fcPular'; p.type = 'button'; p.textContent = 'Pular esta nota';
    p.onclick = () => { window.__fcPular = true; };
    document.body.appendChild(p);
  }
  alvo.classList.add('fc-alvo');
  return true;
})()`;
const JS_TIRA_FAIXA = `(() => { ['fcEstilo','fcFaixa','fcPular'].forEach((i) => { const e = document.getElementById(i); if (e) e.remove(); }); document.querySelectorAll('.fc-alvo').forEach((e) => e.classList.remove('fc-alvo')); })()`;
const JS_CAPTCHA = `(() => {
  const r = document.querySelector('[name="h-captcha-response"], [name="g-recaptcha-response"]');
  return { tem: !!document.querySelector('.h-captcha, iframe[src*="hcaptcha"], [name="h-captcha-response"]'), ok: !!(r && r.value), pular: !!window.__fcPular };
})()`;
const JS_CHAVE = (ch) => `(() => {
  const vis = (e) => e && e.offsetParent !== null;
  let i = document.querySelector('input[id*="ChaveAcesso" i], input[name*="ChaveAcesso" i]');
  if (!i) i = [...document.querySelectorAll('input[type="text"], input:not([type])')].find((x) => vis(x) && (+x.maxLength >= 44 || /chave/i.test(x.id + x.name)));
  if (!i) return false;
  i.focus(); i.value = ${JSON.stringify(ch)};
  i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})()`;
const JS_CLICA = (re) => `(() => {
  const re = ${re};
  const el = [...document.querySelectorAll('input[type="submit"], input[type="button"], button, a')]
    .find((x) => re.test((x.value || x.innerText || x.textContent || '').trim()));
  if (!el) return false;
  window.confirm = () => true; window.alert = () => {};
  el.click(); return true;
})()`;
// mensagem de erro do portal (chave inválida, NF-e inexistente, captcha recusado…)
const JS_ERRO = `(() => {
  const el = [...document.querySelectorAll('[id*="Erro" i], [id*="Msg" i], [class*="erro" i], .validation-summary-errors')].find((x) => x.offsetParent !== null && x.innerText.trim());
  return el ? el.innerText.replace(/\\s+/g, ' ').trim().slice(0, 300) : '';
})()`;
// tabela "Eventos da NF-e" (consulta completa): uma linha por evento (nome, protocolo, data de autorização, inclusão no AN)
const JS_EVENTOS = `(() => {
  const t = (el) => (el ? (el.tagName === 'INPUT' ? el.value : el.innerText) : '').replace(/\\s+/g, ' ').trim();
  const corpo = document.body.innerText || '';
  const sit = (corpo.match(/Situa[çc][ãa]o Atual:\\s*([A-ZÇÃÕÁÉÍÓÚÂÊ ]+?)\\s*\\(/i) || [])[1] || '';
  let tab = null;
  for (const x of document.querySelectorAll('table')) {
    const h = x.innerText || '';
    if (/Eventos da NF-?e/i.test(h) && /Protocolo/i.test(h) && (!tab || h.length < tab.innerText.length)) tab = x;
  }
  const linhas = [];
  if (tab) for (const tr of tab.rows) {
    const c = [...tr.cells].map((td) => t(td.querySelector('input, span') && td.querySelectorAll('input, span').length === 1 ? td.querySelector('input, span') : td));
    if (c.length >= 3 && !/^Eventos da NF/i.test(c[0]) && /\\d{2}\\/\\d{2}\\/\\d{4}/.test(c.join(' '))) linhas.push(c);
  }
  if (!linhas.length) {
    const re = /^(.+?)\\s+(\\d{12,20})\\s+(\\d{2}\\/\\d{2}\\/\\d{4} às [\\d:]+[-+]\\d{2}:\\d{2})\\s+(\\d{2}\\/\\d{2}\\/\\d{4} às [\\d:]+)/gm;
    let m; while ((m = re.exec(corpo))) linhas.push([m[1], m[2], m[3], m[4]]);
  }
  return { achou: !!tab || linhas.length > 0, sit, linhas, completa: /Eventos da NF-?e/i.test(corpo), url: location.href };
})()`;

const TIPOS = [
  [/autoriza[çc][ãa]o de uso/i, '_aut', ''],
  [/ci[êe]ncia da opera/i, '210210', 'ciencia'],
  [/confirma[çc][ãa]o da opera/i, '210200', 'confirmada'],
  [/desconhecimento/i, '210220', 'desconhecida'],
  [/n[ãa]o realizada/i, '210240', 'nao_realizada'],
  [/carta de corre/i, '110110', 'carta_correcao'],
  [/^cancelamento\b(?! do)/i, '110111', 'cancelamento'],
  [/comprovante de entrega/i, '110130', 'comprovante_entrega'],
];
// "15/10/2026 às 10:37:51-03:00" → "2026-10-15T10:37:51-03:00"
function _iso(s) {
  const m = String(s || '').match(/(\d{2})\/(\d{2})\/(\d{4})\D+(\d{2}:\d{2}(?::\d{2})?)([-+]\d{2}:\d{2})?/);
  if (!m) return '';
  return `${m[3]}-${m[2]}-${m[1]}T${m[4].length === 5 ? m[4] + ':00' : m[4]}${m[5] || '-03:00'}`;
}
function _eventos(linhas) {
  const out = { eventos: [], autorizacao: null };
  for (const [nomeBruto, prot, dhAut, dhAn] of linhas) {
    const orgao = (String(nomeBruto).match(/Órg[ãa]o Autor:\s*([^)]+)\)/i) || [])[1] || '';
    const nome = String(nomeBruto).replace(/\s*\(.*$/, '').trim();
    const t = TIPOS.find(([re]) => re.test(nome));
    const ev = { tipo: t ? t[1] : '', nome: t && t[2] ? t[2] : nome, quando: _iso(dhAut), protocolo: _so(prot), orgao: orgao.trim(), inclusaoAN: _iso(dhAn) };
    if (ev.tipo === '_aut') out.autorizacao = ev; else out.eventos.push(ev);
  }
  return out;
}

// Espera a pessoa marcar o "Sou humano" (só o quadro do captcha aparece). Devolve 'ok', 'pular' ou 'parar'.
async function _captcha(titulo) {
  await _js(JS_SO_CAPTCHA(titulo)).catch(() => false);
  _mostrar();
  const fim = Date.now() + ESPERA_CAPTCHA;
  while (Date.now() < fim) {
    if (_parar || !_vivo()) return 'parar';
    let s = {};
    try { s = await _js(JS_CAPTCHA); } catch (_) {}
    if (s.pular) { _log('a pessoa pulou esta nota'); return 'pular'; }
    if (s.ok) { _log('"Sou humano" marcado'); break; }
    if (!s.tem) break;                        // a página mudou sozinha
    await _sleep(500);
  }
  if (Date.now() >= fim) { _log('tempo esgotado esperando o "Sou humano"'); _win.hide(); return 'pular'; }
  _win.hide();
  await _js(JS_TIRA_FAIXA).catch(() => {});
  return 'ok';
}

// Uma chave. Devolve { ok, eventos, autorizacao, situacao } ou { erro, motivo }.
async function _umaChave(item, n, total) {
  _certFaltou = false;
  const w = _janela(item.cnpjEmpresa);
  const titulo = `Eventos da NF-e ${Number(item.numero).toLocaleString('pt-BR')}${total > 1 ? ` · nota ${n} de ${total}` : ''}`;
  await w.loadURL(URL_RESUMO).catch((e) => _log(`erro ao abrir o portal: ${e.message || e}`));
  await _carregou();
  if (!(await _js(JS_CHAVE(item.chave)).catch(() => false))) { await _foto(); return { erro: 'site', motivo: 'O portal da NF-e não abriu a consulta (campo da chave não encontrado).' }; }
  let r = await _captcha(titulo);
  if (r !== 'ok') return { erro: r };
  if (!(await _js(JS_CLICA('/^continuar$/i')).catch(() => false))) { await _foto(); return { erro: 'site', motivo: 'Botão "Continuar" não encontrado no portal.' }; }
  await _carregou();
  // o captcha pode ter sido recusado: a página volta pedindo de novo
  for (let tent = 0; tent < 2; tent++) {
    const msg = await _js(JS_ERRO).catch(() => '');
    const cap = await _js(JS_CAPTCHA).catch(() => ({}));
    const temCompleta = await _js(`!![...document.querySelectorAll('input,button,a')].find((x) => /Consulta Completa/i.test(x.value || x.innerText || ''))`).catch(() => false);
    if (temCompleta) break;
    if (cap.tem && !cap.ok) {
      _log(`o portal pediu o captcha de novo${msg ? `: ${msg}` : ''}`);
      await _js(JS_CHAVE(item.chave)).catch(() => {});
      r = await _captcha(titulo);
      if (r !== 'ok') return { erro: r };
      await _js(JS_CLICA('/^continuar$/i')).catch(() => {});
      await _carregou();
      continue;
    }
    await _foto();
    return { erro: 'site', motivo: msg || 'O portal não mostrou a nota.' };
  }
  // Consulta Completa → OK do aviso → certificado da empresa
  await _js(JS_CLICA('/Consulta Completa/i')).catch(() => false);
  await _carregou(40000);
  for (let i = 0; i < 40; i++) {
    if (_certFaltou) { await _foto(); return { erro: 'cert' }; }
    const cap = await _js(JS_CAPTCHA).catch(() => ({}));
    const ev = await _js(JS_EVENTOS).catch(() => ({}));
    if (ev.achou || ev.completa) {
      const x = _eventos(ev.linhas || []);
      _log(`eventos lidos: ${(ev.linhas || []).length} linha(s) · situação ${ev.sit || '?'}`);
      if (!(ev.linhas || []).length) await _foto();
      return { ok: true, ...x, situacao: String(ev.sit || '').trim().toLowerCase() };
    }
    if (cap.tem && !cap.ok) {                       // a consulta completa também pediu "Sou humano"
      r = await _captcha(titulo);
      if (r !== 'ok') return { erro: r };
      await _js(JS_CLICA('/^continuar$|consultar/i')).catch(() => {});
      await _carregou(40000);
    }
    await _sleep(700);
  }
  await _foto();
  return { erro: 'site', motivo: (await _js(JS_ERRO).catch(() => '')) || 'O portal não mostrou os eventos da nota.' };
}

// itens: [{ chave, numero, cnpjEmpresa }]. progresso({ feitas, total, chave }) a cada nota.
async function eventos(itens, progresso) {
  _parar = false;
  const out = {};
  const instalados = await cnpjsInstalados();
  try {
    for (let i = 0; i < itens.length; i++) {
      const it = itens[i];
      if (_parar) { out[it.chave] = { erro: 'parar' }; continue; }
      if (process.platform === 'win32' && !instalados.includes(it.cnpjEmpresa)) { out[it.chave] = { erro: 'cert' }; continue; }
      try { if (progresso) progresso({ feitas: i, total: itens.length, chave: it.chave }); } catch (_) {}
      _log(`— chave ${it.chave}`);
      try { out[it.chave] = await _umaChave(it, i + 1, itens.length); } catch (e) { _log(`erro: ${e.message || e}`); out[it.chave] = { erro: _parar ? 'parar' : 'site', motivo: String(e.message || e).slice(0, 200) }; }
      if (out[it.chave].erro === 'parar') _parar = true;
    }
  } finally {
    if (_vivo()) _win.destroy();
    _win = null;
  }
  try { if (progresso) progresso({ feitas: itens.length, total: itens.length }); } catch (_) {}
  return out;
}
function parar() { _parar = true; if (_vivo()) _win.hide(); }

module.exports = { init, eventos, parar, cnpjsInstalados, _eventos, _iso };
