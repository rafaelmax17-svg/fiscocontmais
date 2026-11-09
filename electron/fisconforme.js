'use strict';
// Acompanhamento das notificações do FISCONFORME (SEFIN-RO, Decreto 23.856/2019) — só o Admin, por enquanto.
//
// • Entra no portal com o e-CPF do contador instalado no Windows (SSO da SEFIN, aba "Acesso via cert. digital"),
//   numa janela escondida, sem captcha: se aparecer captcha, o robô para e avisa.
// • Lê SÓ as listas (pendente, contestado, indeferido, resolvido). NUNCA abre a notificação por conta própria: abrir o
//   conteúdo conta como ciência e começa o prazo (art. 3º, § 3º). O "Visualizar" só roda quando o Admin pede e confirma.
// • Guarda tudo na nuvem (coleção fisconforme, regra: só o Admin) — um documento por notificação (código), com a data em
//   que o robô viu pela primeira vez, a situação e desde quando. Documentos que começam com "_" são controle.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, BrowserWindow } = require('electron');
const { execFile } = require('child_process');
const auth = require('./auth');

const BASE = 'https://fisconforme.sefin.ro.gov.br';
const LISTAS = ['pendente', 'contestado', 'indeferido', 'resolvido'];
const MAX_PAG = { pendente: 200, contestado: 50, indeferido: 50, resolvido: 80 };
const COL = 'fisconforme';
const PARTICAO = 'persist:fisconforme';

let D = null;                      // { userData, notificar(canal, dados) }
let _win = null, _cpfAtivo = '', _rodando = false;

function init(deps) {
  D = deps;
  // certificado do cliente (TLS): só para a janela do robô, escolhe o e-CPF configurado
  app.on('select-client-certificate', (event, webContents, url, lista, callback) => {
    if (!_win || _win.isDestroyed() || webContents.id !== _win.webContents.id) return;
    const alvo = lista.find((c) => _cpfDoCert(c) === _cpfAtivo);
    _log(`o site pediu certificado (${url.split('?')[0]}): ${lista.length} disponível(is) · ${alvo ? 'usando o e-CPF do contador' : 'o e-CPF escolhido NÃO está na lista'}`);
    event.preventDefault();
    callback(alvo || undefined);
  });
}

const _cfgPath = () => path.join(D.userData(), 'fisconforme.json');
function _cfg() { try { return JSON.parse(fs.readFileSync(_cfgPath(), 'utf-8')); } catch (_) { return {}; } }
function _grava(c) { fs.writeFileSync(_cfgPath(), JSON.stringify(c, null, 1)); }
function _ehAdmin() { const s = auth.sessao(); return !!(s && s.perfil === 'admin'); }
// Fisconforme liberado para a equipe: Admin, Fiscal (padrão do perfil) ou quem recebeu o módulo na lista de módulos liberados
function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes('fiscal-fisconforme') : s.perfil === 'fiscal';
}
function _exige() { if (!podeUsar()) throw new Error('Sem acesso ao módulo Fisconforme.'); }
function _exigeAdmin() { if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.'); }
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
const _so = (s) => String(s || '').replace(/\D/g, '');
function _cpfDoCert(c) {
  const cn = String((c.subject && c.subject.commonName) || c.subjectName || '');
  const m = cn.match(/:(\d{11})\b/);
  return m ? m[1] : '';
}
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let _canal = 'fisc:progresso';            // o módulo de DARE usa a mesma entrada e troca o canal do progresso
function _prog(txt, extra) { try { D.notificar(_canal, { txt, ...(extra || {}) }); } catch (_) {} }

// ------------------------------------------------------------------ certificados e-CPF instalados no Windows
function certificados() {
  return new Promise((resolve) => {
    if (process.platform !== 'win32') { resolve({ certs: [], aviso: 'Disponível só no Windows.' }); return; }
    const ps = "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey } | "
      + "Select-Object Subject, Issuer, Thumbprint, @{n='Vence';e={$_.NotAfter.ToString('yyyy-MM-dd')}} | ConvertTo-Json -Compress";
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true, timeout: 30000 }, (err, out) => {
      if (err) { resolve({ certs: [], aviso: 'Não consegui ler os certificados do Windows.' }); return; }
      let lst = [];
      try { const j = JSON.parse(out || '[]'); lst = Array.isArray(j) ? j : [j]; } catch (_) {}
      const hoje = new Date().toISOString().slice(0, 10);
      const certs = lst.map((c) => {
        const cn = (String(c.Subject || '').match(/CN=([^,]+)/) || [])[1] || '';
        const m = cn.match(/^(.*):(\d{11})$/);
        return m ? { nome: m[1].trim(), cpf: m[2], vence: c.Vence || '', vencido: (c.Vence || '9') < hoje, emissor: ((String(c.Issuer || '').match(/CN=([^,]+)/) || [])[1] || '') } : null;
      }).filter(Boolean);
      resolve({ certs });
    });
  });
}

async function estado() {
  _exige();
  const { certs, aviso } = await certificados();
  const c = _cfg();
  const escolhido = certs.find((x) => x.cpf === c.cpf) || (certs.length === 1 ? certs[0] : null);
  if (escolhido && (c.cpf !== escolhido.cpf || c.nome !== escolhido.nome)) _grava({ ...c, cpf: escolhido.cpf, nome: escolhido.nome });
  return { certs, aviso: aviso || '', cpf: escolhido ? escolhido.cpf : '', escolhido: escolhido || null, mostrarJanela: !!c.mostrarJanela };
}
function escolherCert(cpf) { _exige(); _grava({ ..._cfg(), cpf: _so(cpf) }); return { ok: true }; }

// ------------------------------------------------------------------ janela do robô e login
// Entrada pelo certificado (o mesmo link que o contador usa no navegador): o SSO de certificado pede o e-CPF no TLS,
// mostra nome e CPF e o botão "Entrar", e volta para o Fisconforme.
const URL_CERT = 'https://sitafesec-sso-int.sefin.ro.gov.br/acesso_externo/acesso_digital?request_url='
  + encodeURIComponent(`${BASE}/contribuintes/pendente`) + '&login_template=default';
const _ehSso = (host) => /(^|\.)sitafe[\w-]*\.sefin\.ro\.gov\.br$/i.test(host || '');

// Registro passo a passo (fisconforme_log.txt na pasta de dados) — ajuda a ajustar o robô no primeiro uso.
let _logTxt = [];
function _log(m) {
  const l = `${new Date().toLocaleTimeString('pt-BR')} ${m}`;
  _logTxt.push(l);
  try { fs.writeFileSync(path.join(D.userData(), 'fisconforme_log.txt'), _logTxt.slice(-400).join('\n')); } catch (_) {}
}

function _janela() {
  if (_win && !_win.isDestroyed()) return _win;
  const mostrar = !!_cfg().mostrarJanela;
  _win = new BrowserWindow({ show: mostrar, width: 1200, height: 860, title: 'FiscoCont+ · Fisconforme', autoHideMenuBar: true,
    webPreferences: { partition: PARTICAO, contextIsolation: true, nodeIntegration: false, sandbox: true } });
  _win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  _win.webContents.on('did-navigate', (_e, url) => _log(`abriu ${url.split('?')[0]}`));
  _win.webContents.on('did-fail-load', (_e, cod, desc, url) => { if (cod !== -3) _log(`falha ao abrir ${String(url).split('?')[0]}: ${desc} (${cod})`); });
  _win.webContents.on('certificate-error', (_e, url, err) => _log(`erro de certificado do site ${url}: ${err}`));
  return _win;
}
// loadURL com limite de tempo: o portal às vezes não termina de carregar e a promessa nunca resolveria
async function _vai(url, limite = 45000) {
  const w = _janela();
  let venceu = false;
  const t = new Promise((r) => setTimeout(() => { venceu = true; r(); }, limite));
  await Promise.race([w.loadURL(url).catch((e) => { if (!/ERR_ABORTED/.test(String(e))) _log(`loadURL: ${e.message || e}`); }), t]);
  if (venceu) { _log(`demorou mais de ${limite / 1000}s: ${url.split('?')[0]}`); try { w.webContents.stop(); } catch (_) {} }
  await _sleep(500);
  return w;
}
const _js = (code) => Promise.race([_win.webContents.executeJavaScript(code, true), new Promise((_r, rej) => setTimeout(() => rej(new Error('a página não respondeu')), 20000))]);

const JS_ESTADO_LOGIN = `(() => {
  const vis = (e) => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const txt = (document.body ? document.body.innerText : '').slice(0, 5000);
  const captcha = !!document.querySelector('iframe[src*="captcha"], .g-recaptcha, .h-captcha, [data-sitekey]');
  const els = [...document.querySelectorAll('a, button, li, [role=tab], .nav-link, input[type=submit]')].filter(vis);
  const aba = els.find((e) => /cert\\.?\\s*digital/i.test(e.innerText || e.value || ''));
  const entrar = els.find((e) => /^\\s*entrar\\s*$/i.test(e.innerText || e.value || '') && !e.disabled);
  return { url: location.href, captcha, temAba: !!aba, temEntrar: !!entrar, mostraCpf: /\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}/.test(txt),
           texto: txt.replace(/\\s+/g, ' ').slice(0, 300) };
})()`;
const JS_CLICA_ENTRAR = `(() => { const vis = (e) => !!(e && (e.offsetWidth || e.offsetHeight));
  const b = [...document.querySelectorAll('button, input[type=submit], a')].filter(vis).find((e) => /^\\s*entrar\\s*$/i.test(e.innerText || e.value || '') && !e.disabled);
  if (b) { b.click(); return true; } return false; })()`;

async function _logado() {
  const u = new URL(_win.webContents.getURL() || 'about:blank');
  if (u.host !== 'fisconforme.sefin.ro.gov.br') return false;
  return _js(`!!document.querySelector('a[href*="sso/logout"]')`).catch(() => false);
}

async function _login() {
  const c = _cfg();
  if (!c.cpf) throw new Error('Escolha o certificado (e-CPF) do contador na tela do módulo.');
  _cpfAtivo = c.cpf;
  _prog('Entrando no portal da SEFIN com o certificado do contador…');
  // já logado (sessão guardada)? vai direto
  await _vai(`${BASE}/contribuintes/pendente`, 30000);
  if (await _logado()) { _log('sessão ainda válida'); return true; }
  _log('abrindo o acesso por certificado digital');
  await _vai(URL_CERT, 60000);
  const ate = Date.now() + 90000;
  let clicouEntrar = 0, ultimoTxt = '';
  while (Date.now() < ate) {
    if (await _logado()) { _log('entrou no Fisconforme'); return true; }
    const u = new URL(_win.webContents.getURL() || 'about:blank');
    if (_ehSso(u.host)) {
      const st = await _js(JS_ESTADO_LOGIN).catch(() => null);
      if (st && st.texto !== ultimoTxt) { _log(`tela do SSO: ${st.texto}`); ultimoTxt = st.texto; }
      if (st && st.captcha) throw new Error('O portal pediu captcha e a consulta parou. Entre uma vez pelo navegador e tente de novo depois.');
      if (st && st.temEntrar && clicouEntrar < 3) {
        _prog('Confirmando o acesso com o e-CPF do contador…');
        await _js(JS_CLICA_ENTRAR); clicouEntrar++; _log('clicou em Entrar'); await _sleep(3000); continue;
      }
    } else if (u.host === 'fisconforme.sefin.ro.gov.br' || /portalcontribuinte\.sefin\.ro\.gov\.br/.test(u.host)) {
      await _vai(`${BASE}/contribuintes/pendente`, 30000);
      continue;
    }
    await _sleep(1500);
  }
  try { const img = await _win.webContents.capturePage(); fs.writeFileSync(path.join(D.userData(), 'fisconforme_login.png'), img.toPNG()); } catch (_) {}
  if (!_ehAdmin()) throw new Error('Não consegui entrar no portal com o certificado do contador. Tente de novo em alguns minutos; se continuar, avise o Admin.');
  throw new Error('Não consegui entrar no portal com o certificado do contador. Ligue "Mostrar a janela da consulta" na tela e tente de novo para ver onde parou. '
    + 'Um print da última tela e o passo a passo ficaram em "fisconforme_login.png" e "fisconforme_log.txt", na pasta de dados do FiscoCont+.');
}

function mostrarJanela(sim) { _exigeAdmin(); _grava({ ..._cfg(), mostrarJanela: !!sim }); return { ok: true }; }
function abrirPastaDados() { const { shell } = require('electron'); shell.openPath(D.userData()); return { ok: true }; }

// ------------------------------------------------------------------ leitura das listas
const JS_LISTA = `(() => {
  const rows = [...document.querySelectorAll('table.table > tbody > tr')].map((tr) => {
    const td = [...tr.children].filter((e) => e.tagName === 'TD');
    if (td.length < 5) return null;
    const t = (i) => (td[i].innerText || '').replace(/\\s+/g, ' ').trim();
    return { codigo: t(0), ie: t(1), nome: t(2), periodo: t(3), desc: t(4) };
  }).filter((r) => r && /^\\d+$/.test(r.codigo));
  const pags = [...document.querySelectorAll('ul.pagination a')].map((a) => { const m = (a.getAttribute('href') || '').match(/page=(\\d+)/); return m ? +m[1] : 1; });
  const emps = [...document.querySelectorAll('#busca_contribuinte option')].map((o) => ({ cnpj: (o.value || '').trim(), t: (o.textContent || '').replace(/\\s+/g, ' ').trim() })).filter((x) => x.cnpj);
  const malhas = [...document.querySelectorAll('#busca_malha option')].map((o) => ({ cod: (o.value || '').trim(), nome: (o.textContent || '').replace(/\\s+/g, ' ').trim() })).filter((x) => x.cod);
  const logado = !!document.querySelector('a[href*="sso/logout"]');
  return { rows, max: Math.max(1, ...pags), emps, malhas, logado, url: location.href };
})()`;

async function _lerLista(nome) {
  const out = [];
  let max = 1, emps = [], malhas = [];
  for (let p = 1; p <= Math.min(max, MAX_PAG[nome]); p++) {
    _prog(`Lendo "${nome}" · página ${p}${max > 1 ? ` de ${max}` : ''}…`);
    await _vai(`${BASE}/contribuintes/${nome}${p > 1 ? `?page=${p}` : ''}`);
    let r = await _js(JS_LISTA);
    if (!r.logado) {                                   // sessão caiu no meio: entra de novo e repete a página
      await _login();
      await _vai(`${BASE}/contribuintes/${nome}${p > 1 ? `?page=${p}` : ''}`);
      r = await _js(JS_LISTA);
      if (!r.logado) throw new Error('A sessão do portal caiu e não voltou.');
    }
    if (p === 1) { max = r.max; emps = r.emps; malhas = r.malhas; }
    r.rows.forEach((x) => out.push({ ...x, pagina: p }));
    await _sleep(350);
  }
  return { linhas: out, paginas: Math.min(max, MAX_PAG[nome]), emps, malhas };
}

const _n = (s) => String(s || '').toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Z0-9]+/g, ' ').trim();

// IE + nome da linha → CNPJ, pela lista de empresas vinculadas ao contador (o próprio portal traz essa lista)
function _mapaEmpresas(emps) {
  const lst = emps.map((e) => {
    const m = e.t.match(/^(\d*)\s*-\s*(.+)$/);
    return { cnpj: _so(e.cnpj), ie: m ? m[1] : '', nome: m ? m[2].trim() : e.t };
  });
  return (ie, nome) => {
    const n = _n(nome);
    const a = lst.filter((x) => x.ie === ie && _n(x.nome) === n);
    if (new Set(a.map((x) => x.cnpj)).size === 1) return a[0].cnpj;
    const b = lst.filter((x) => _n(x.nome) === n);
    if (new Set(b.map((x) => x.cnpj)).size === 1) return b[0].cnpj;
    const c = lst.filter((x) => x.ie === ie);
    if (new Set(c.map((x) => x.cnpj)).size === 1) return c[0].cnpj;
    return '';
  };
}

async function ler() {
  _exige();
  if (_rodando) throw new Error('Há uma consulta da SEFIN em andamento. Aguarde terminar.');
  _rodando = true; _canal = 'fisc:progresso';
  _logTxt = [];
  const inicio = new Date();
  const lid = inicio.toISOString();
  try {
    await _login();
    const res = {};
    let emps = [], malhas = [];
    for (const l of LISTAS) {
      const r = await _lerLista(l);
      res[l] = r;
      if (r.emps.length > emps.length) emps = r.emps;
      if (r.malhas.length > malhas.length) malhas = r.malhas;
    }
    _prog('Gravando…');
    const cnpjDe = _mapaEmpresas(emps);
    const codMalha = new Map(malhas.map((m) => [_n(m.nome), m.cod]));
    const { db, f } = _fs();
    const ant = new Map();
    (await f.getDocs(f.collection(db, COL))).forEach((d) => { if (!d.id.startsWith('_')) ant.set(d.id, d.data()); });
    const visto = new Map();
    for (const l of LISTAS) for (const x of res[l].linhas) if (!visto.has(x.codigo)) visto.set(x.codigo, { ...x, status: l });
    const hoje = lid.slice(0, 10);
    const gravar = [];
    for (const [cod, x] of visto) {
      const a = ant.get(cod) || {};
      const doc = {
        codigo: cod, ie: x.ie, nome: x.nome, cnpj: cnpjDe(x.ie, x.nome) || a.cnpj || '', periodo: x.periodo, desc: x.desc,
        malha: codMalha.get(_n(x.desc)) || a.malha || '', status: x.status, pagina: x.pagina,
        primeiraVez: a.primeiraVez || hoje, primeiraLeitura: a.primeiraLeitura || lid,
        statusDesde: a.status === x.status ? (a.statusDesde || hoje) : hoje, ultimaVez: hoje, ultimaLeitura: lid,
      };
      const muda = ['status', 'cnpj', 'periodo', 'desc', 'malha', 'pagina', 'nome'].some((k) => doc[k] !== a[k]) || !a.codigo;
      if (muda || a.ultimaVez !== hoje) gravar.push([cod, doc]);
    }
    for (const [cod, a] of ant) {                      // sumiu de todas as listas
      if (!visto.has(cod) && a.status !== 'fora') gravar.push([cod, { ...a, status: 'fora', statusDesde: hoje, ultimaLeitura: lid }]);
    }
    for (let i = 0; i < gravar.length; i += 400) {
      const b = f.writeBatch(db);
      gravar.slice(i, i + 400).forEach(([cod, d]) => b.set(f.doc(db, COL, cod), d, { merge: true }));
      await b.commit();
    }
    const cont = Object.fromEntries(LISTAS.map((l) => [l, res[l].linhas.length]));
    const novas = [...visto.keys()].filter((c) => !ant.has(c)).length;
    const ses = auth.sessao() || {};
    await f.setDoc(f.doc(db, COL, '_meta'), {
      ultimaLeitura: lid, por: ses.nome || ses.email || '', duracaoSeg: Math.round((Date.now() - inicio) / 1000),
      paginas: Object.fromEntries(LISTAS.map((l) => [l, res[l].paginas])), contagens: cont, novas,
      primeiraLeituraGeral: (await f.getDoc(f.doc(db, COL, '_meta'))).data()?.primeiraLeituraGeral || lid,
      malhas: malhas.map((m) => ({ cod: m.cod, nome: m.nome })),
      contador: { nome: _cfg().nome || '', cpf: _cpfAtivo || '' },
    }, { merge: true });
    _prog('', { fim: true });
    return { ok: true, contagens: cont, novas };
  } catch (e) {
    _log(`parou: ${e.message || e}`);
    throw e;
  } finally {
    _rodando = false;
    if (_win && !_win.isDestroyed()) { _win.destroy(); _win = null; }
  }
}

// ------------------------------------------------------------------ painel (lê da nuvem)
async function dados() {
  _exige();
  const { db, f } = _fs();
  const notif = [], extras = {};
  let meta = null;
  (await f.getDocs(f.collection(db, COL))).forEach((d) => {
    if (d.id === '_meta') meta = d.data();
    else if (d.id.startsWith('_m_')) extras[d.id.slice(3)] = d.data();
    else notif.push(d.data());
  });
  return { notif, meta, explicMalha: extras, rodando: _rodando };
}

// resumo para o ícone do menu: só o documento _meta (não lê as notificações)
async function resumo() {
  _exige();
  const { db, f } = _fs();
  const m = (await f.getDoc(f.doc(db, COL, '_meta'))).data() || null;
  return { pendentes: m && m.contagens ? (m.contagens.pendente || 0) : null, novas: m ? (m.novas || 0) : 0,
    primeira: !!m && m.ultimaLeitura === m.primeiraLeituraGeral };
}

// ------------------------------------------------------------------ explicação (sem dados do cliente)
async function explicarMalha(cod, nome) {
  _exige();
  const { db, f } = _fs();
  const ref = f.doc(db, COL, `_m_${String(cod || _n(nome).slice(0, 40)).replace(/[^\w]/g, '_')}`);
  const s = await f.getDoc(ref);
  if (s.exists() && s.data().texto) return { texto: s.data().texto, em: s.data().em || '' };
  const r = await auth.explicarFisconforme({ malha: nome });
  const em = new Date().toLocaleDateString('pt-BR');
  await f.setDoc(ref, { texto: r.texto, malha: nome, em });
  return { texto: r.texto, em };
}

// Visualizar = DÁ CIÊNCIA (só depois da confirmação do Admin na tela). Abre a lista da página onde a notificação
// estava, chama o "Visualizar" do próprio portal, lê o texto da janela que abre e grava com a data da ciência.
async function visualizar(codigo) {
  _exige();
  if (_rodando) throw new Error('Há uma consulta da SEFIN em andamento. Aguarde terminar.');
  _rodando = true; _canal = 'fisc:progresso';
  try {
    const { db, f } = _fs();
    const ref = f.doc(db, COL, String(codigo));
    const s = await f.getDoc(ref);
    if (!s.exists()) throw new Error('Notificação não encontrada. Faça uma leitura antes.');
    const n = s.data();
    await _login();
    await _vai(`${BASE}/contribuintes/${n.status === 'fora' ? 'pendente' : n.status}${n.pagina > 1 ? `?page=${n.pagina}` : ''}`);
    const existe = await _js(`typeof visualizar_contribuinte === 'function' && !![...document.querySelectorAll('table.table > tbody > tr > td:first-child')].find((t) => t.innerText.trim() === ${JSON.stringify(String(codigo))})`);
    if (!existe) throw new Error('A notificação não está mais na página em que foi lida. Faça uma nova leitura e tente de novo.');
    await _js(`visualizar_contribuinte(${Number(codigo)})`);
    let texto = '';
    for (let i = 0; i < 30 && !texto; i++) {
      await _sleep(700);
      texto = await _js(`(() => { const m = [...document.querySelectorAll('.modal')].filter((e) => e.offsetWidth || e.offsetHeight || e.classList.contains('in') || getComputedStyle(e).display === 'block');
        const t = m.map((e) => (e.querySelector('.modal-content') || e).innerText.replace(/\\n{3,}/g, '\\n\\n').trim()).filter((x) => x.length > 60);
        return t.sort((a, b) => b.length - a.length)[0] || ''; })()`);
    }
    if (!texto) throw new Error('O portal não mostrou o conteúdo da notificação.');
    const ciencia = new Date().toLocaleString('pt-BR');
    const prazo = (texto.match(/prazo[^\n.]{0,80}?(\d{2}\/\d{2}\/\d{4})/i) || [])[1] || '';
    // explicação desta notificação: o texto vai sem CNPJ, CPF, IE e sem o nome da empresa
    let explic = '';
    try {
      let anon = texto;
      if (n.nome) anon = anon.split(n.nome).join('[EMPRESA]');
      anon = anon.replace(/\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/g, '[CNPJ]').replace(/\d{3}\.?\d{3}\.?\d{3}-?\d{2}/g, '[CPF]').replace(/\b\d{9,14}\b/g, '[IE]');
      explic = (await auth.explicarFisconforme({ malha: n.desc, periodo: n.periodo, detalhe: anon })).texto;
    } catch (_) {}
    const ses = auth.sessao() || {};
    await f.setDoc(ref, { detalhe: texto.slice(0, 20000), cienciaEm: ciencia, cienciaPor: ses.nome || ses.email || '', prazo, explicacao: explic }, { merge: true });
    return { ok: true, detalhe: texto, cienciaEm: ciencia, prazo, explicacao: explic };
  } finally {
    _rodando = false;
    if (_win && !_win.isDestroyed()) { _win.destroy(); _win = null; }
  }
}

// Entrada por certificado e janela compartilhadas com o módulo Débitos e DARE (electron/dare.js).
// Uma consulta por vez: as duas telas usam a mesma janela e a mesma sessão da SEFIN.
const portal = {
  janela: () => _janela(), vai: (u, l) => _vai(u, l), js: (c) => _js(c), win: () => _win,
  log: (m) => _log(m), limpaLog: () => { _logTxt = []; }, prog: (t, x) => _prog(t, x), canal: (c) => { _canal = c; },
  loginSso: () => _login(), cfg: () => _cfg(), ehAdmin: () => _ehAdmin(), ehSso: _ehSso, sleep: _sleep,
  JS_ESTADO_LOGIN, JS_CLICA_ENTRAR,
  ocupado: () => _rodando,
  ocupar() { if (_rodando) throw new Error('Há uma consulta da SEFIN em andamento. Aguarde terminar.'); _rodando = true; },
  liberar(fechar = true) { _rodando = false; if (fechar && _win && !_win.isDestroyed()) { _win.destroy(); _win = null; } },
};

module.exports = { portal, init, podeUsar, resumo, estado, escolherCert, ler, dados, explicarMalha, visualizar, certificados, mostrarJanela, abrirPastaDados };
