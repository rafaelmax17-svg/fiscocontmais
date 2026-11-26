'use strict';
const { app, BrowserWindow, ipcMain, dialog, shell, safeStorage, net } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const childProcess = require('child_process');
// Todo processo filho (núcleos Python, PowerShell) fica registrado e é encerrado ao fechar o sistema.
// Achado real (24/10): um núcleo ainda aberto travava os arquivos e a atualização falhava com
// "Falha ao desinstalar os arquivos do aplicativo antigo".
const _filhos = new Set();
function spawn(...a) {
  const ch = childProcess.spawn(...a);
  _filhos.add(ch);
  ch.on('exit', () => _filhos.delete(ch));
  ch.on('error', () => _filhos.delete(ch));
  return ch;
}
function _encerraFilhos() {
  for (const ch of _filhos) {
    try {
      if (process.platform === 'win32' && ch.pid) childProcess.spawnSync('taskkill', ['/pid', String(ch.pid), '/T', '/F'], { windowsHide: true });
      else ch.kill();
    } catch (_) {}
  }
  _filhos.clear();
}
const cloud = require('./cloudSync');
const license = require('./license');
const changelog = require('./changelog');
const nfseLote = require('./nfseLote');
let updater;
try {
  updater = require('./updater');
} catch (_) {
  updater = { initAutoUpdate: () => {}, checkNow: async () => {}, installNow: () => {} };
}

const APP_NAME = 'FiscoCont+';
let mainWindow = null;
let lastRealtimeLicenseStatus = null; // achado: o evento de status podia chegar ANTES do renderer
                                        // registrar o listener (corrida na inicialização) e se perdia
                                        // pra sempre — guarda aqui pra dar pra consultar sob demanda também
let splashWindow = null;
let lastPdfPath = null;
let lastJsonPath = null; // caminho do balancete já parseado (cache) — evita reabrir o PDF em telas sob demanda (Indicadores)

// ---------------------------------------------------------------------------
// Resolve o executável do núcleo Python (dev = interpretador, prod = .exe)
// ---------------------------------------------------------------------------
function pythonCore() {
  if (app.isPackaged) {
    const bin = process.platform === 'win32' ? 'balancete_core.exe' : 'balancete_core';
    return { cmd: path.join(process.resourcesPath, 'bin', bin), baseArgs: [] };
  }
  const script = path.join(__dirname, '..', 'python', 'balancete_core.py');
  let py = process.env.FISCOCONT_PYTHON;
  if (!py) {
    const venv = path.join(
      __dirname, '..', '.venv',
      process.platform === 'win32' ? path.join('Scripts', 'python.exe') : path.join('bin', 'python')
    );
    py = fs.existsSync(venv) ? venv : (process.platform === 'win32' ? 'python' : 'python3');
  }
  return { cmd: py, baseArgs: [script] };
}

function logoPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'assets', 'liddera-logo.png')
    : path.join(__dirname, '..', 'assets', 'liddera-logo.png');
}

function runCore(args, readyFile, validate) {
  return new Promise((resolve, reject) => {
    const { cmd, baseArgs } = pythonCore();
    let child;
    try {
      child = spawn(cmd, [...baseArgs, ...args], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', FISCOCONT_LOGO: logoPath() },
        windowsHide: true,
      });
    } catch (e) {
      return reject(new Error('Não foi possível iniciar o núcleo (' + cmd + '): ' + e.message));
    }

    let out = '', err = '', done = false, poll = null, lastSize = -1;
    const finish = (fn, val) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (poll) clearInterval(poll);
      try { child.kill(); } catch (_) {}
      fn(val);
    };
    const timer = setTimeout(() => {
      finish(reject, new Error('Tempo esgotado (40s) ao processar o balancete. O núcleo iniciou mas não retornou — pode ser o antivírus bloqueando o balancete_core.exe, ou um PDF fora do padrão do Domínio.'));
    }, 40000);

    // resolve assim que o arquivo de saída estiver pronto (não espera o processo "fechar")
    if (readyFile) {
      poll = setInterval(() => {
        try {
          if (!fs.existsSync(readyFile)) return;
          const size = fs.statSync(readyFile).size;
          if (size <= 0) return;
          if (validate === 'json') {
            const txt = fs.readFileSync(readyFile, 'utf-8');
            JSON.parse(txt);                       // só resolve com JSON íntegro
            finish(resolve, { stdout: out, file: txt });
          } else {
            if (size === lastSize) finish(resolve, { stdout: out }); // tamanho estável = escrito
            lastSize = size;
          }
        } catch (_) { /* ainda escrevendo — tenta de novo */ }
      }, 200);
    }

    if (child.stdout) child.stdout.on('data', (d) => (out += d.toString()));
    if (child.stderr) child.stderr.on('data', (d) => (err += d.toString()));
    try { child.stdin && child.stdin.end(); } catch (_) {}
    child.on('error', (e) => finish(reject, new Error('Falha ao executar o núcleo (' + cmd + '): ' + e.message)));
    child.on('close', (code) => {
      if (code === 0) finish(resolve, { stdout: out });
      else finish(reject, new Error(((err || out) || '').trim() || ('O núcleo encerrou com código ' + code)));
    });
  });
}

// ---------------------------------------------------------------------------
// Janelas
// ---------------------------------------------------------------------------
// Tela de abertura: só aparece depois de desenhada (antes aparecia vazia enquanto carregava e, numa máquina mais
// lenta, a animação começava quase na hora de fechar). O tempo mínimo conta a partir do momento em que ela aparece,
// e a janela principal só começa a carregar depois disso, para não disputar a máquina com a animação.
const SPLASH_MIN_MS = 5000;       // a animação termina em ~4 s (barra de carregamento); o resto é para ver a tela completa
let splashShownAt = 0;
function createSplash(onShown) {
  splashWindow = new BrowserWindow({
    width: 720,
    height: 470,
    frame: false,
    resizable: false,
    transparent: true,
    alwaysOnTop: true,
    center: true,
    show: false,
    skipTaskbar: true,
    webPreferences: { contextIsolation: true, backgroundThrottling: false },
  });
  let feito = false;
  const mostrar = () => {
    if (feito) return;
    feito = true;
    if (splashWindow) splashWindow.show();
    splashShownAt = Date.now();
    setTimeout(onShown, 250);      // deixa a animação começar antes de carregar o sistema
  };
  splashWindow.once('ready-to-show', mostrar);
  setTimeout(mostrar, 2500);       // segurança: se a tela de abertura travar, o sistema abre assim mesmo
  splashWindow.loadFile(path.join(__dirname, 'splash.html'), { query: { v: app.getVersion() } });
}

function fecharSplash(depois) {
  const w = splashWindow;
  splashWindow = null;
  if (!w || w.isDestroyed()) { depois(); return; }
  w.webContents.executeJavaScript("document.body.classList.add('sai')").catch(() => {});
  setTimeout(() => { depois(); setTimeout(() => { if (!w.isDestroyed()) w.close(); }, 120); }, 380);
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1040,
    minHeight: 680,
    show: false,
    frame: false,
    backgroundColor: '#0f1225',
    title: APP_NAME,
    icon: path.join(__dirname, '..', 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const sendMax = () => mainWindow && mainWindow.webContents.send('win:maximized', mainWindow.isMaximized());
  mainWindow.on('maximize', sendMax);
  mainWindow.on('unmaximize', sendMax);

  mainWindow.setMenuBarVisibility(false);
  // Manual do Fiscal aberto: sem ferramentas de desenvolvedor, salvar, imprimir ou recarregar pela tecla
  mainWindow.webContents.on('before-input-event', (ev, inp) => {
    if (!_manualAberto || inp.type !== 'keyDown') return;
    const k = String(inp.key || '').toLowerCase(), ctrl = inp.control || inp.meta;
    if (k === 'f12' || (ctrl && inp.shift && ['i', 'j', 'c'].includes(k)) || (ctrl && ['s', 'p', 'r', 'u'].includes(k))) ev.preventDefault();
  });
  mainWindow.webContents.on('devtools-opened', () => { if (_manualAberto) mainWindow.webContents.closeDevTools(); });
  // relatórios em HTML (ex.: lote de NFS-e) trazem links relativos para os painéis salvos nas pastas dos clientes:
  // abrir no navegador padrão em vez de uma janela nova do app
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('file:')) {
      try { shell.openPath(require('url').fileURLToPath(url)); } catch (_) {}
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });
  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  // 2.4.47: se a janela não ficar pronta em 12 s (antivírus/driver bloqueando a placa de vídeo), reabre sem aceleração
  // de vídeo; se já estiver sem aceleração, mostra a janela assim mesmo (antes o sistema ficava aberto sem tela)
  const _mwSeguranca = setTimeout(() => {
    if (!mainWindow || mainWindow.isDestroyed() || mainWindow.isVisible()) return;
    if (_reabrirSemGpu('a janela não foi desenhada em 12 s')) return;
    fecharSplash(() => { if (mainWindow && !mainWindow.isDestroyed()) { mainWindow.maximize(); mainWindow.show(); } });
  }, 12000);
  mainWindow.once('ready-to-show', () => {
    clearTimeout(_mwSeguranca);
    const wait = splashWindow ? Math.max(0, SPLASH_MIN_MS - (Date.now() - (splashShownAt || Date.now()))) : 0;
    setTimeout(() => {
      fecharSplash(() => {
        if (!mainWindow) return;
        mainWindow.maximize(); // sempre abre em tela cheia (login incluso, é a mesma janela)
        mainWindow.show();
      });
    }, wait);
  });

  mainWindow.on('closed', () => (mainWindow = null));
}

// Uma janela só: abrir o atalho de novo traz a janela que já está aberta (dois FiscoCont+ ao mesmo tempo
// travavam arquivos durante a atualização).
// Aceleração de vídeo LIGADA (as animações dependem dela). Se numa máquina a placa de vídeo for bloqueada (caso real de
// 25/11: antivírus → a janela nunca era desenhada), o sistema grava a marca "sem-gpu.flag" e reabre sozinho sem
// aceleração. A marca vale só para a versão em que aconteceu: na próxima atualização ele tenta de novo com a placa.
let _semGpuArq = '', _semGpu = false;
try { _semGpuArq = path.join(String(app.getPath('userData')), 'sem-gpu.flag'); } catch (_) {}
try {
  if (_semGpuArq && fs.existsSync(_semGpuArq)) {
    _semGpu = fs.readFileSync(_semGpuArq, 'utf-8').split(' ')[0] === app.getVersion();
    if (!_semGpu) fs.unlinkSync(_semGpuArq);
  }
} catch (_) {}
if (_semGpu || process.argv.includes('--sem-gpu') || process.argv.includes('--disable-gpu')) app.disableHardwareAcceleration();
function _reabrirSemGpu(motivo) {
  if (_semGpu || !_semGpuArq) return false;
  try { fs.writeFileSync(_semGpuArq, `${app.getVersion()} ${new Date().toISOString()} ${motivo}`); } catch (_) { return false; }
  app.relaunch(); app.exit(0);
  return true;
}
app.on('child-process-gone', (_e, d) => { if (d && d.type === 'GPU') _reabrirSemGpu('a placa de vídeo parou: ' + (d.reason || '')); });
const _instanciaPrincipal = app.requestSingleInstanceLock();
if (!_instanciaPrincipal) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.show(); mainWindow.focus(); return; }
    // 2.4.46: o processo ficou vivo sem janela (ex.: fechou no meio de uma tarefa) → abrir o atalho de novo não fazia
    // nada. Agora recria a janela.
    if (app.isReady()) createMainWindow();
  });
}

// Ao sair: fecha os núcleos e, se houver atualização baixada, instala em silêncio e reabre o sistema sozinho.
let _saindo = false;
app.on('before-quit', (ev) => {
  _encerraFilhos();
  if (!_saindo && updater && updater.temAtualizacao && updater.temAtualizacao()) {
    _saindo = true;
    ev.preventDefault();
    setTimeout(() => updater.installNow(false), 300);
  }
});

app.whenReady().then(() => {
  if (!_instanciaPrincipal) return;
  createSplash(() => createMainWindow());
  // 2.1: a credencial de administrador do Firebase não fica mais em nenhuma máquina
  cloud.removerCredencialAntiga(app.getPath('userData'));
  auth.limpaOfflineAntigo(app.getPath('userData'));

  updater.initAutoUpdate(() => mainWindow);
  setTimeout(() => updater.checkNow(), 15000); // não compete com a abertura do app

  // achado real (Rafael, 30/09): NÃO começa por um tempo fixo chutado —
  // a tela só está pronta pra RECEBER o balão depois que registra o
  // listener (o que só acontece depois do await checkLicenseGate() no
  // app.js, que pode demorar mais que qualquer número fixo numa rede mais
  // lenta). Se checar antes disso, a notícia é "enviada" sem ninguém
  // ouvindo do outro lado e se perde — foi exatamente isso que aconteceu:
  // 20 notícias marcadas como vistas, nenhuma apareceu. Agora espera a
  // própria tela avisar que está pronta (ver 'news:rendererPronto' abaixo).

  // Bloqueio remoto em tempo real: assim que o Admin ativa/bloqueia esta
  // máquina no Firestore, o app fica sabendo em segundos.
  license.startLicenseListener(
    (data) => { if (mainWindow) mainWindow.webContents.send('license:changed', data); },
    (status) => {
      lastRealtimeLicenseStatus = status;
      if (mainWindow) mainWindow.webContents.send('license:realtimeStatus', status);
    }
  ).catch((e) => {
    const status = { ok: false, motivo: 'erro_inicial', erro: String((e && e.message) || e) };
    lastRealtimeLicenseStatus = status;
    if (mainWindow) mainWindow.webContents.send('license:realtimeStatus', status);
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (lastJsonPath) { try { fs.unlinkSync(lastJsonPath); } catch (_) {} }
  if (newsTimer) clearInterval(newsTimer);
  if (process.platform !== 'darwin') app.quit();
});

// ---------------------------------------------------------------------------
// Canal de notícias contábeis (letreiro na faixa do topo)
// ---------------------------------------------------------------------------
// Fonte: RSS oficial do Portal Contábeis — pesquisei e testei antes de
// implementar (28/09): feed real, atualiza a cada 30min-1h em dia útil,
// bem estruturado (título/link/categoria). Só mostra as categorias que o
// Rafael pediu (Simples Nacional já vem classificado como "Tributário" na
// própria fonte, não precisa de regra à parte). Checa a cada 3 min — não
// muda quantos balões aparecem (isso depende do ritmo de publicação do
// site), só reduz o atraso até a equipe ver uma notícia nova.
const NEWS_RSS_URL = 'https://www.contabeis.com.br/rss/noticias/';
const NEWS_CATEGORIAS_PERMITIDAS = ['Tributário', 'Contábil', 'Empresarial'];
const NEWS_INTERVALO_MS = 40 * 1000;
let newsTimer = null;

function _newsConfigPath() {
  return path.join(app.getPath('userData'), 'news-config.json');
}
function _newsLerConfig() {
  try { return JSON.parse(fs.readFileSync(_newsConfigPath(), 'utf-8')); }
  catch (_) { return { desativado: false, vistos: [] }; }
}
function _newsSalvarConfig(cfg) {
  try { fs.writeFileSync(_newsConfigPath(), JSON.stringify(cfg)); } catch (_) {}
}

// Parser simples e direto pro formato real do feed (testado contra a
// resposta de verdade do Portal Contábeis) — sem precisar de dependência
// nova só pra isso.
function _newsParseRss(xml) {
  const itens = [];
  const blocos = xml.split('<item>').slice(1);
  for (const bloco of blocos) {
    const corpo = bloco.split('</item>')[0];
    const pega = (tag) => {
      const m = corpo.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${tag}>`));
      return m ? m[1].trim() : '';
    };
    const catM = corpo.match(/<category[^>]*>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/category>/);
    itens.push({ titulo: pega('title'), link: pega('link'), guid: pega('guid'), categoria: catM ? catM[1].trim() : '' });
  }
  return itens;
}

// Registro de diagnóstico das últimas tentativas — como não dá pra testar
// contra o site de verdade daqui (rede do ambiente de build bloqueia esse
// domínio), guardo os últimos resultados (sucesso e erro) pra conseguir
// investigar de longe se algo ainda falhar.
function _newsLogPath() {
  return path.join(app.getPath('userData'), 'news-log.json');
}
function _newsLog(entrada) {
  let log = [];
  try { log = JSON.parse(fs.readFileSync(_newsLogPath(), 'utf-8')); } catch (_) {}
  log.unshift({ quando: new Date().toISOString(), ...entrada });
  try { fs.writeFileSync(_newsLogPath(), JSON.stringify(log.slice(0, 30), null, 2)); } catch (_) {}
}

// Busca a URL seguindo redirecionamentos (até 5) e descompactando a
// resposta de acordo com o Content-Encoding que o servidor mandar — sem
// isso, um servidor que comprime a resposta (comum, mesmo sem eu pedir)
// faria o programa receber dado ilegível e nunca achar nenhuma notícia,
// sem erro nenhum aparecer. Foi o suspeito mais forte do problema relatado.
function _newsBuscarUrl(url, tentativas, cb) {
  const https = require('https');
  const zlib = require('zlib');
  if (tentativas <= 0) { cb(new Error('Redirecionado demais vezes')); return; }
  https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) FiscoCont+/1.0',
      'Accept': 'application/rss+xml, application/xml, text/xml, */*',
      'Accept-Encoding': 'gzip, deflate, br',
    },
  }, (res) => {
    if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
      res.resume();
      const proximo = new URL(res.headers.location, url).toString();
      _newsBuscarUrl(proximo, tentativas - 1, cb);
      return;
    }
    if (res.statusCode !== 200) {
      res.resume();
      cb(new Error(`HTTP ${res.statusCode}`));
      return;
    }
    const codificacao = (res.headers['content-encoding'] || '').toLowerCase();
    let fluxo = res;
    try {
      if (codificacao === 'gzip') fluxo = res.pipe(zlib.createGunzip());
      else if (codificacao === 'deflate') fluxo = res.pipe(zlib.createInflate());
      else if (codificacao === 'br') fluxo = res.pipe(zlib.createBrotliDecompress());
    } catch (e) { cb(e); return; }
    let dados = '';
    fluxo.on('data', (d) => { dados += d; });
    fluxo.on('end', () => cb(null, dados, codificacao || 'nenhuma'));
    fluxo.on('error', (e) => cb(e));
  }).on('error', (e) => cb(e));
}

function _newsChecar() {
  const cfg = _newsLerConfig();
  if (cfg.desativado || !mainWindow) return;
  _newsBuscarUrl(NEWS_RSS_URL, 5, (erro, dados, codificacao) => {
    if (erro) { _newsLog({ ok: false, motivo: String(erro.message || erro) }); return; }
    try {
      const todos = _newsParseRss(dados);
      const permitidos = todos.filter((i) => NEWS_CATEGORIAS_PERMITIDAS.includes(i.categoria));
      // Faixa de notícias no topo (substituiu o balão, 26/10): manda a lista das mais recentes; a tela só
      // redesenha o letreiro quando a lista muda.
      const lista = permitidos.slice(0, 15).map((i) => ({ titulo: i.titulo, link: i.link, categoria: i.categoria, guid: i.guid || i.link }));
      _newsLog({ ok: true, codificacao, itensNoFeed: todos.length, naFaixa: lista.length });
      if (lista.length && mainWindow) mainWindow.webContents.send('news:lista', lista);
    } catch (e) { _newsLog({ ok: false, motivo: 'Erro ao interpretar o feed: ' + String(e.message || e) }); }
  });
}

ipcMain.handle('news:status', () => (_newsLerConfig().desativado ? 'desativado' : 'ativo'));
ipcMain.handle('news:desativar', () => { const c = _newsLerConfig(); c.desativado = true; _newsSalvarConfig(c); return true; });
ipcMain.handle('news:ativar', () => { const c = _newsLerConfig(); c.desativado = false; _newsSalvarConfig(c); setTimeout(_newsChecar, 200); return true; });
ipcMain.handle('news:abrirLink', (_evt, url) => { if (/^https:\/\//.test(url || '')) shell.openExternal(url); });

// A tela avisa por aqui quando já registrou o listener de notícia — só a
// partir desse aviso o relógio de checagem começa (substitui o tempo fixo
// chutado, que foi a causa real do balão nunca aparecer).
let newsRendererPronto = false;
ipcMain.on('news:rendererPronto', () => {
  if (newsRendererPronto) return; // só uma vez, mesmo que a tela recarregue
  newsRendererPronto = true;
  _newsChecar();
  newsTimer = setInterval(_newsChecar, NEWS_INTERVALO_MS);
});

// ---------------------------------------------------------------------------
// IPC: escolher o PDF (sem overlay durante a seleção)
// ---------------------------------------------------------------------------
// ---- Login individual (e-mail e senha · Firebase Authentication) ----
// Cada pessoa tem o próprio usuário; o perfil (Fiscal / Contábil / Admin) vem do cadastro na nuvem e só o Admin
// cadastra, bloqueia ou muda perfil (electron/auth.js + firestore.rules). Nenhuma senha fica no código.
// A sessão trava depois de um tempo sem uso (15 min Admin, 60 min demais) e pede a senha de novo.
const auth = require('./auth');
let sessionRole = null;   // perfil da sessão atual (trava os módulos exclusivos do Admin)
let sessionLocked = false;
let sessionModulos = null;   // módulos liberados pelo Admin (null = padrão do perfil)
// Módulos de Administração que o Admin pode liberar para outra pessoa (Usuários e Licenças continuam só do Admin).
const ADMIN_EXCLUSIVOS = new Set(['admin-usuarios', 'admin-lic']);
const TEMPO_TRAVA_MIN = { admin: 40, fiscal: 60, contabil: 60 };
function _sessaoPublica() {
  const s = auth.sessao();
  return s ? { email: s.email, nome: s.nome, perfil: s.perfil, offline: !!s.offline, travaMin: TEMPO_TRAVA_MIN[s.perfil] || 60,
               modulos: s.modulos || null, trocarSenha: !!s.trocarSenha } : null;
}
ipcMain.handle('auth:login', async (_evt, { email, senha, salvar, usarSalva } = {}) => {
  const r = await auth.login(app.getPath('userData'), email, senha, (info) => {
    if (info.motivo === 'bloqueado') sessionRole = null;
    else if (info.motivo === 'perfil') { sessionRole = info.perfil; sessionModulos = info.modulos || null; }
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('auth:mudou', info);
  }, { salvar, usarSalva });
  if (!r.ok) return { ok: false, erro: r.erro, semInternet: !!r.semInternet, info: !!r.info };
  sessionRole = r.perfil;
  sessionModulos = r.modulos || null;
  sessionLocked = !!r.trocarSenha;     // senha provisória: nada funciona até a pessoa criar a própria senha
  license.marcarUsuario(r.email);
  if (r.perfil === 'admin' && !r.trocarSenha) integra.iniciarRobo().catch(() => {});   // só liga se a chave estiver neste computador
  return { ok: true, role: r.perfil, aviso: r.aviso || '', sessao: _sessaoPublica() };
});
ipcMain.handle('auth:logout', () => { fechamento.parar(); integra.pararRobo(); auth.logout(); sessionRole = null; sessionLocked = false; return { ok: true }; });
ipcMain.handle('auth:sessao', () => _sessaoPublica());
ipcMain.handle('auth:travar', () => { if (sessionRole) sessionLocked = true; return { ok: true }; });
ipcMain.handle('auth:destravar', async (_evt, senha) => {
  if (!sessionRole) return { ok: false, erro: 'Sessão encerrada. Entre de novo.' };
  const c = await auth.confereSenha(app.getPath('userData'), senha);
  if (!c.ok) return { ok: false, erro: c.erro };
  sessionLocked = false;
  return { ok: true };
});
ipcMain.handle('auth:trocarSenha', async (_evt, { nova, salvar } = {}) => {
  const r = await auth.trocarSenha(app.getPath('userData'), nova, salvar);
  if (r.ok) sessionLocked = false;
  return r;
});
ipcMain.handle('auth:conectado', async () => ({ ok: await auth.conectado() }));
ipcMain.handle('auth:salvo', () => auth.salvoPublico(app.getPath('userData')));
ipcMain.handle('auth:esquecerSalvo', () => { auth.salvoApagar(app.getPath('userData')); return { ok: true }; });
ipcMain.handle('auth:redefinirSenha', async (_evt, email) => auth.redefinirSenha(email));
ipcMain.handle('auth:primeiroAcesso', async (_evt, { email, senha } = {}) => auth.criarAdminInicial(email, senha));

// Cadastro de usuários (só Admin)
// Módulo liberado nas configurações do usuário (Usuários › Módulos): Admin sempre; demais só se o módulo estiver na lista.
// Liberado = acesso completo ao módulo, igual ao Admin.
const _podeModulo = (id) => {
  if (sessionRole === 'admin') return true;
  const s = auth.sessao() || {};
  return Array.isArray(s.modulos) && s.modulos.includes(id);
};
const _mod = (id) => async (fn) => {
  if (!_podeModulo(id)) return { error: 'Este módulo não está liberado para você. Peça ao Admin para liberar em Usuários › Módulos.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
const _adm = async (fn) => {
  if (sessionRole !== 'admin') return { error: 'Acesso restrito ao Admin.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
// ---------------------------------------------------------------- Manual do Fiscal (leitura protegida)
// Enquanto o manual está aberto: a janela fica protegida contra print/gravação/compartilhamento de tela
// (sai preta) e as ferramentas de desenvolvedor não abrem. Nada é gravado em disco: as páginas vêm da nuvem.
const manual = require('./manual');
let _manualAberto = false;
function _manualProtecao(on) {
  _manualAberto = !!on;
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try { mainWindow.setContentProtection(_manualAberto); } catch (_) {}
  if (_manualAberto && mainWindow.webContents.isDevToolsOpened()) mainWindow.webContents.closeDevTools();
}
const _man = async (fn) => {
  if (sessionLocked) return { error: 'Sessão travada por inatividade: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String((e && e.message) || e) }; }
};
ipcMain.handle('manual:info', () => _man(() => manual.info()));
ipcMain.handle('manual:pagina', (_evt, i) => _man(() => manual.pagina(i)));
ipcMain.handle('manual:protecao', (_evt, on) => { _manualProtecao(on); return { ok: true }; });
ipcMain.handle('manual:acessoInicio', () => _man(() => manual.acessoInicio()));
ipcMain.handle('manual:acessoFim', (_evt, { id, segundos }) => _man(() => manual.acessoFim(id, segundos)));
ipcMain.handle('manual:acessos', () => _adm(() => manual.acessos()));
ipcMain.handle('manual:publicar', () => _adm(async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Pasta do manual (manual.json + imagens das páginas)', properties: ['openDirectory'] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  return manual.publicar(r.filePaths[0]);
}));

// ---------------------------------------------------------------- Simples Nacional · Fechamento da equipe
const fechamento = require('./fechamento');
const _fech = async (fn) => {
  if (sessionLocked) return { error: 'Sessão travada por inatividade: digite a senha para continuar.' };
  try { return await fn(); } catch (e) { return { error: String((e && e.message) || e) }; }
};
ipcMain.handle('fech:abrir', (_evt, comp) => _fech(async () => {
  await fechamento.abrir(comp);
  fechamento.ouvir(comp, (dados) => { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('fech:mudou', dados); });
  return { ok: true };
}));
ipcMain.handle('fech:parar', () => { fechamento.parar(); return { ok: true }; });
ipcMain.handle('fech:salvar', (_evt, { comp, id, campo, valor }) => _fech(() => fechamento.salvar(comp, id, campo, valor)));
ipcMain.handle('fech:cadastrar', (_evt, { comp, dados }) => _fech(() => fechamento.cadastrar(comp, dados || {})));
ipcMain.handle('fech:alterar', (_evt, { comp, id, mud }) => _fech(() => fechamento.alterar(comp, id, mud || {})));
ipcMain.handle('fech:inativar', (_evt, { comp, id }) => _fech(() => fechamento.inativar(comp, id)));
ipcMain.handle('fech:analistaNova', (_evt, nome) => _fech(() => fechamento.analistaNova(nome)));
ipcMain.handle('fech:analistaRemover', (_evt, nome) => _fech(() => fechamento.analistaRemover(nome)));
ipcMain.handle('fech:cancelarRetif', (_evt, { comp, id }) => _fech(() => fechamento.cancelarRetif(comp, id)));
ipcMain.handle('fech:reativar', (_evt, { comp, id }) => _fech(() => fechamento.reativar(comp, id)));
// ---- Robô do Fechamento · Integra Contador (Serpro) — chave só neste computador, cifrada (electron/integra.js)
const integra = require('./integra');
integra.init({
  userData: () => app.getPath('userData'),
  runFiscal: (args, pronto) => runFiscal(args, pronto),
  maquina: () => license.getMachineCode(),
  // certId escolhido neste computador; sem ele (ou se sumiu), o e-CNPJ do contratante com a validade mais longa
  credEscritorio: (certId, raiz) => {
    const indice = _lerIndiceCert();
    const mat = indice.empresas.filter((x) => (x.tipo || 'matriz') === 'matriz');
    const c = mat.find((x) => x.id === certId)
      || mat.filter((x) => String(x.cnpj || '').slice(0, 8) === raiz).sort((a, b) => String(b.validade || '').localeCompare(String(a.validade || '')))[0];
    if (!c) return { error: 'O e-CNPJ da Liddera não está cadastrado nas Baixas DF-e deste computador.' };
    return _credDe(indice, c);
  },
  pastaFallback: () => {
    try { const p = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; if (p) return p; } catch (_) {}
    try { if (fs.existsSync(PASTA_PADRAO_NFSE)) return PASTA_PADRAO_NFSE; } catch (_) {}
    return '';
  },
});
// ---- Fisconforme (SEFIN-RO): notificações de todas as empresas, com o e-CPF do contador (electron/fisconforme.js)
// Liberado para a equipe (Admin, Fiscal ou quem recebeu o módulo). Só o Admin: navegador do robô, pasta de dados e abrir o portal.
const fisconforme = require('./fisconforme');
fisconforme.init({ userData: () => app.getPath('userData'), notificar: (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} } });
const _fisc = async (fn) => {
  if (!fisconforme.podeUsar()) return { error: 'Sem acesso ao módulo Fisconforme.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
ipcMain.handle('fisc:estado', () => _fisc(() => fisconforme.estado()));
ipcMain.handle('fisc:escolherCert', (_evt, cpf) => _fisc(() => fisconforme.escolherCert(cpf)));
ipcMain.handle('fisc:ler', () => _fisc(() => fisconforme.ler()));
ipcMain.handle('fisc:dados', () => _fisc(() => fisconforme.dados()));
ipcMain.handle('fisc:resumo', () => _fisc(() => fisconforme.resumo()));
ipcMain.handle('fisc:explicarMalha', (_evt, { cod, nome }) => _fisc(() => fisconforme.explicarMalha(cod, nome)));
ipcMain.handle('fisc:visualizar', (_evt, codigo) => _fisc(() => fisconforme.visualizar(codigo)));
// baixa em lote (21/11/2026): a pasta é deste computador
ipcMain.handle('fisc:baixarLote', (_evt, o) => _fisc(() => fisconforme.baixarLote(o || {})));
ipcMain.handle('fisc:pararLote', () => _fisc(() => fisconforme.pararLote()));
ipcMain.handle('fisc:pastaLote', () => _fisc(() => fisconforme.pastaLote()));
ipcMain.handle('fisc:escolherPastaLote', async () => _fisc(async () => {
  const atual = fisconforme.pastaLote().pasta;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Pasta onde salvar as notificações do Fisconforme', defaultPath: atual || app.getPath('documents'), properties: ['openDirectory', 'createDirectory'] });
  if (r.canceled || !r.filePaths || !r.filePaths[0]) return { canceled: true, pasta: atual };
  return fisconforme.definirPastaLote(r.filePaths[0]);
}));
ipcMain.handle('fisc:abrirPastaLote', () => _fisc(async () => {
  const p = fisconforme.pastaLote().pasta;
  if (!p || !fs.existsSync(p)) throw new Error('A pasta das notificações não está acessível neste computador.');
  await shell.openPath(p); return {};
}));
ipcMain.handle('fisc:mostrarJanela', (_evt, sim) => _adm(() => fisconforme.mostrarJanela(sim)));
ipcMain.handle('fisc:pastaDados', () => _adm(() => fisconforme.abrirPastaDados()));
// ---- Débitos e DARE (SEFIN-RO · Portal do Contribuinte): mesma entrada por certificado do Fisconforme (electron/dare.js)
const dfeSefin = require('./dfe_sefin');
dfeSefin.init({
  pastaDe: (emp, pasta) => _dfeBaseDe(emp, pasta),
  userData: () => app.getPath('userData'),
  notificar: (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} },
  runFiscal: (args, out) => runFiscal(args, out),
  pastaBase: () => { try { return JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) { return ''; } },
});
const dare = require('./dare');
dare.init({ userData: () => app.getPath('userData'), notificar: (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} } });
const _dare = async (fn) => {
  if (!dare.podeUsar()) return { error: 'Sem acesso ao módulo Débitos e DARE.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
// consulta automática da SEFIN (Fisconforme + Débitos): 4x por dia, no primeiro FiscoCont+ aberto com o e-CPF do contador
const agendaSefin = require('./agenda_sefin');
agendaSefin.init({ notificar: (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} } });
ipcMain.handle('sefin:agenda', () => ({ ok: true, ...agendaSefin.estado() }));
// ---- Recibos GIAM/SPED Fiscal (SEFIN-RO · Portal do Contribuinte, e-CPF do contador) — electron/giam.js
const giam = require('./giam');
giam.init({ userData: () => app.getPath('userData'), cnpjApi: (c) => _cnpjApiCache(c), notificar: (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} } });
const _giam = async (fn) => {
  if (!giam.podeUsar()) return { error: 'Sem acesso ao módulo Recibos GIAM/SPED.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
ipcMain.handle('giam:dados', (_evt, comp) => _giam(async () => ({ ...(await giam.dados(comp || giam.compAnterior())), compPadrao: giam.compAnterior(), proxima: (agendaSefin.estado().proximoGiam || '') })));
ipcMain.handle('giam:ler', (_evt, o) => _giam(() => giam.ler((o && o.comp) || giam.compAnterior(), { ie: o && o.ie })));
ipcMain.handle('giam:abrir', (_evt, { caminho, pasta }) => _giam(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('Arquivo não encontrado neste computador (o recibo pode ter sido salvo em outro computador sem o drive G:, ou foi movido).');
  if (pasta) shell.showItemInFolder(caminho); else await shell.openPath(caminho);
  return {};
}));

// ---- Conferência da EFD-Reinf (serviço oficial de consulta · certificado do escritório) — 2.4.6/2.4.14 (electron/reinf.js e agenda_reinf.js)
const reinf = require('./reinf');
const _notifica = (c, d) => { try { mainWindow && mainWindow.webContents.send(c, d); } catch (_) {} };
reinf.init({
  userData: () => app.getPath('userData'), notificar: _notifica, runFiscal: (args, out) => runFiscal(args, out), janelaPai: () => mainWindow,
  empresasLocais: () => (_lerIndiceCert().empresas || []).filter((e) => (e.tipo || 'matriz') !== 'procuracao').map((e) => ({ cnpj: e.cnpj, nome: e.razaoSocial })),
});
// REINF × DCTFWeb (2.4.9): conferência e transmissão pelo Integra Contador; o robô do Admin atende (electron/dctfweb.js)
const dctfweb = require('./dctfweb');
dctfweb.init({ userData: () => app.getPath('userData'), notificar: _notifica });
ipcMain.handle('dctf:dados', (_evt, comp) => _reinf(() => dctfweb.dados(comp || agendaReinf.compAnterior())));
ipcMain.handle('dctf:pedir', (_evt, o) => _reinf(() => dctfweb.pedir(o || {})));
ipcMain.handle('dctf:abrir', (_evt, { caminho }) => _reinf(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('O recibo não está acessível neste computador (pasta do cliente no Drive).');
  await shell.openPath(caminho);
  return {};
}));
// MIT · PIS e COFINS (2.4.26): EFD-Contribuições → MIT pela Receita, em nome do procurador (e-CPF); o robô do Admin atende
const mitMod = require('./mit');
mitMod.init({ userData: () => app.getPath('userData'), notificar: _notifica, runFiscal: (args, out) => runFiscal(args, out) });
const _mit = async (fn) => {
  if (!mitMod.podeUsar()) return { error: 'Sem acesso ao módulo MIT.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
ipcMain.handle('mit:dados', (_evt, comp) => _mit(() => mitMod.dados(comp)));
ipcMain.handle('mit:escolherEfd', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'EFD-Contribuições (pode escolher várias empresas)', properties: ['openFile', 'multiSelections'], filters: [{ name: 'EFD-Contribuições', extensions: ['txt'] }] });
  return r.canceled ? { canceled: true } : { paths: r.filePaths };
});
ipcMain.handle('mit:importar', (_evt, arquivos) => _mit(() => mitMod.importar(arquivos)));
ipcMain.handle('mit:salvarEmpresa', (_evt, o) => _mit(() => mitMod.salvarEmpresa(o || {})));
ipcMain.handle('mit:pedir', (_evt, o) => _mit(() => mitMod.pedir(o || {})));
// 2.4.60: recibo não salvo porque o nome da pasta não bate → a equipe aponta a pasta da empresa ali mesmo
ipcMain.handle('mit:escolherPasta', async (_evt, o = {}) => {
  const pc = require('./pasta_cliente');
  const ini = pc.RAIZES.find((r) => { try { return fs.statSync(r).isDirectory(); } catch (_) { return false; } });
  const r = await dialog.showOpenDialog(mainWindow, { title: `Pasta da empresa no drive${o.nome ? ` · ${o.nome}` : ''}`, defaultPath: ini || undefined, properties: ['openDirectory'] });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return _mit(() => mitMod.definirPasta({ cnpj: o.cnpj, comp: o.comp, dir: r.filePaths[0] }));
});
ipcMain.handle('mit:auto', (_evt, ligado) => _mit(() => mitMod.configAuto(!!ligado)));
ipcMain.handle('mit:limparHistorico', (_evt, comp) => _mit(() => mitMod.limparHistorico(comp)));
ipcMain.handle('mit:abrir', (_evt, { caminho }) => _mit(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('O arquivo não está acessível neste computador (pasta do cliente no Drive).');
  await shell.openPath(caminho);
  return {};
}));
const agendaReinf = require('./agenda_reinf');
agendaReinf.init({ notificar: _notifica, ocupado: () => { try { return fisconforme.portal.ocupado(); } catch (_) { return false; } } });
const _reinf = async (fn) => {
  if (!reinf.podeUsar()) return { error: 'Sem acesso ao módulo EFD-Reinf.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String(e.message || e) }; }
};
ipcMain.handle('reinf:dados', (_evt, comp) => _reinf(async () => {
  const c = comp || agendaReinf.compAnterior();
  return { ...(await reinf.dados(c)), proxima: agendaReinf.proxima(), compPadrao: agendaReinf.compAnterior(), certificadoAqui: await reinf.certificadoInstalado().catch(() => false) };
}));
ipcMain.handle('reinf:conferir', (_evt, o) => _reinf(() => reinf.conferir(o || {})));
ipcMain.handle('reinf:parar', () => _reinf(async () => reinf.parar()));
ipcMain.handle('reinf:empresas', (_evt, lista) => _reinf(async () => (lista ? reinf.salvarEmpresas(lista) : { lista: await reinf.empresas() })));
ipcMain.handle('reinf:abrir', (_evt, { caminho, pasta }) => _reinf(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('Arquivo não encontrado neste computador (a conferência pode ter sido feita em outro computador, ou o arquivo foi movido).');
  if (pasta) shell.showItemInFolder(caminho); else await shell.openPath(caminho);
  return {};
}));
// "Gerar lista": PDF (página montada na tela, impressa aqui) e Excel (python reinf.py)
ipcMain.handle('reinf:listaPdf', (_evt, { html, nome }) => _reinf(async () => {
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar a lista da EFD-Reinf', defaultPath: path.join(app.getPath('documents'), `${nome || 'EFD-Reinf'}.pdf`), filters: [{ name: 'PDF', extensions: ['pdf'] }] });
  if (r.canceled || !r.filePath) return { cancelado: true };
  const w = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true, javascript: false } });
  try {
    await w.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
    const pdf = await w.webContents.printToPDF({ landscape: true, printBackground: true, pageSize: 'A4', margins: { marginType: 'custom', top: 0.35, bottom: 0.35, left: 0.35, right: 0.35 } });
    fs.writeFileSync(r.filePath, pdf);
  } finally { w.destroy(); }
  shell.openPath(r.filePath);
  return { arquivo: r.filePath };
}));
ipcMain.handle('reinf:listaXlsx', (_evt, { dados, nome }) => _reinf(async () => {
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar a lista da EFD-Reinf', defaultPath: path.join(app.getPath('documents'), `${nome || 'EFD-Reinf'}.xlsx`), filters: [{ name: 'Excel', extensions: ['xlsx'] }] });
  if (r.canceled || !r.filePath) return { cancelado: true };
  const ent = path.join(os.tmpdir(), `fc_reinf_l_${Date.now()}.json`), out = ent.replace(/\.json$/, '_r.json');
  fs.writeFileSync(ent, JSON.stringify(dados));
  try { await runFiscal(['reinf-lista', '--entrada', ent, '--xlsx', r.filePath, '--json', out], out); } finally { fs.unlink(ent, () => {}); }
  const x = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
  if (x.erro) throw new Error(x.erro);
  shell.openPath(r.filePath);
  return { arquivo: r.filePath };
}));
ipcMain.handle('dare:ler', (_evt, ano) => _dare(() => dare.ler(ano)));
ipcMain.handle('dare:dados', (_evt, ano) => _dare(() => dare.dados(ano)));
ipcMain.handle('dare:resumo', (_evt, ano) => _dare(() => dare.resumo(ano)));
ipcMain.handle('dare:previa', (_evt, x) => _dare(() => dare.previa(x)));
ipcMain.handle('dare:preparar', (_evt, x) => _dare(() => dare.preparar(x)));
ipcMain.handle('dare:novoCodigo', () => _dare(() => dare.novoCodigo()));
ipcMain.handle('dare:emitir', (_evt, o) => _dare(() => dare.emitir(o || {})));
ipcMain.handle('dare:cancelar', () => _dare(() => dare.cancelar()));
ipcMain.handle('dare:extrato', (_evt, x) => _dare(() => dare.extrato(x)));
ipcMain.handle('dare:lerPagos', (_evt, mes, opc) => _dare(() => dare.lerPagos(mes, opc || {})));
ipcMain.handle('dare:dadosPagos', (_evt, mes) => _dare(() => dare.dadosPagos(mes)));
ipcMain.handle('dare:extratoPago', (_evt, x) => _dare(() => dare.extratoPago(x)));
// abre o PDF salvo ou a pasta da empresa (só caminhos dentro da pasta dos DAREs)
ipcMain.handle('dare:abrir', (_evt, arq) => _dare(async () => {
  const alvo = path.resolve(String(arq || ''));
  const raiz = path.resolve((require('./fisconforme').portal.cfg().pastaDare) || dare.PASTA_PADRAO);
  if (!alvo.toLowerCase().startsWith(raiz.toLowerCase())) throw new Error('Caminho fora da pasta dos DAREs.');
  if (!fs.existsSync(alvo)) throw new Error('Arquivo não encontrado.');
  const r = await shell.openPath(alvo); if (r) throw new Error(r);
  return {};
}));
ipcMain.handle('dare:exportar', async (_evt, { html, nome }) => {
  if (!dare.podeUsar()) return { error: 'Sem acesso ao módulo Débitos e DARE.' };
  const save = await dialog.showSaveDialog(mainWindow, { title: 'Salvar PDF dos débitos', defaultPath: `${String(nome || 'Débitos SEFIN-RO').replace(/[\\/:*?"<>|]+/g, ' ').trim()}.pdf`, filters: [{ name: 'PDF', extensions: ['pdf'] }] });
  if (save.canceled || !save.filePath) return { canceled: true };
  const tmp = path.join(os.tmpdir(), `fc_dare_${Date.now()}.html`);
  fs.writeFileSync(tmp, String(html), 'utf-8');
  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(tmp); await new Promise((r) => setTimeout(r, 700));
    fs.writeFileSync(save.filePath, await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', landscape: true, margins: { marginType: 'default' } }));
    shell.openPath(save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; } finally { worker.destroy(); fs.unlink(tmp, () => {}); }
});

// Relatório do Fisconforme: o HTML vem pronto da tela; salva como HTML ou converte em PDF (paisagem, sem movimento)
ipcMain.handle('fisc:exportar', async (_evt, { html, formato, nome }) => {
  if (!fisconforme.podeUsar()) return { error: 'Sem acesso ao módulo Fisconforme.' };
  const pdf = formato === 'pdf';
  const save = await dialog.showSaveDialog(mainWindow, {
    title: pdf ? 'Salvar PDF do Fisconforme' : 'Salvar HTML do Fisconforme',
    defaultPath: `${String(nome || 'Fisconforme').replace(/[\\/:*?"<>|]+/g, ' ').trim()}.${pdf ? 'pdf' : 'html'}`,
    filters: [pdf ? { name: 'PDF', extensions: ['pdf'] } : { name: 'Página HTML', extensions: ['html'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  if (!pdf) { fs.writeFileSync(save.filePath, String(html), 'utf-8'); shell.openPath(save.filePath); return { ok: true, path: save.filePath }; }
  const tmp = path.join(os.tmpdir(), `fc_fisc_${Date.now()}.html`);
  const estatico = String(html).replace('</head>', '<style>*,*::before,*::after{animation:none!important;transition:none!important}</style></head>')
    .replace('<body', '<body data-pdf="1"');
  fs.writeFileSync(tmp, estatico, 'utf-8');
  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(tmp);
    await new Promise((r) => setTimeout(r, 900));
    const buf = await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', landscape: true, margins: { marginType: 'default' } });
    fs.writeFileSync(save.filePath, buf);
    shell.openPath(save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { worker.destroy(); fs.unlink(tmp, () => {}); }
});
// PDF da notificação para encaminhar ao cliente: a pessoa escolhe onde salvar (a janela já abre na pasta do cliente)
ipcMain.handle('fisc:pdfCliente', async (_evt, { codigo, orientacao }) => {
  if (!fisconforme.podeUsar()) return { error: 'Sem acesso ao módulo Fisconforme.' };
  let worker = null, tmp = '';
  try {
    const n = await fisconforme.notificacao(codigo);
    if (!n.detalhe) return { error: 'Visualize a notificação antes: o PDF usa o conteúdo lido do portal.' };
    let logo = '';
    try { logo = 'data:image/png;base64,' + fs.readFileSync(path.join(__dirname, '..', 'renderer', 'img', 'liddera-logo.png')).toString('base64'); } catch (_) {}
    const pc = require('./pasta_cliente');
    const hoje = new Date();
    let dir = '';
    try {
      const mes = pc.pastaDoMes({ nome: n.nome, cnpj: n.cnpj }, hoje.getFullYear(), hoje.getMonth() + 1, false);
      const emp = pc.achar({ nome: n.nome, cnpj: n.cnpj });
      dir = [mes, emp && emp.dir].find((d) => d && fs.existsSync(d)) || '';
    } catch (_) {}
    const nome = `Notificação Fisconforme ${n.codigo} - ${n.nome || ''}`.replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 150);
    const save = await dialog.showSaveDialog(mainWindow, {
      title: 'Salvar a notificação em PDF', defaultPath: path.join(dir || app.getPath('documents'), `${nome}.pdf`), filters: [{ name: 'PDF', extensions: ['pdf'] }],
    });
    if (save.canceled || !save.filePath) return { canceled: true };
    tmp = path.join(os.tmpdir(), `fc_notif_${Date.now()}.html`);
    fs.writeFileSync(tmp, fisconforme.htmlCliente(n, orientacao, logo), 'utf-8');
    worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, javascript: false } });
    await worker.loadFile(tmp);
    const buf = await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', preferCSSPageSize: true });
    fs.writeFileSync(save.filePath, buf);
    shell.openPath(save.filePath);
    return { path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { if (worker) worker.destroy(); if (tmp) fs.unlink(tmp, () => {}); }
});
ipcMain.handle('fisc:abrirPortal', () => { if (sessionRole !== 'admin') return { error: 'Acesso restrito ao Admin.' }; shell.openExternal('https://fisconforme.sefin.ro.gov.br/contribuintes/pendente'); return { ok: true }; });

ipcMain.handle('integra:estado', () => _adm(async () => ({ local: await integra.estadoLocal(), nuvem: await integra.estadoNuvem().catch(() => null) })));
ipcMain.handle('integra:salvarChave', (_evt, dados) => _adm(() => integra.salvarChave(dados || {})));
ipcMain.handle('integra:testar', () => _adm(() => integra.testar()));
ipcMain.handle('integra:remover', () => _adm(() => integra.remover()));
ipcMain.handle('integra:salvarPastas', (_evt, dados) => _adm(() => integra.salvarPastas(dados || {})));
ipcMain.handle('integra:definirPasta', (_evt, { id, pasta }) => _adm(() => integra.definirPasta(id, pasta)));
ipcMain.handle('integra:escolherPasta', async (_evt, titulo) => {
  if (sessionRole !== 'admin') return { error: 'Acesso restrito ao Admin.' };
  const r = await dialog.showOpenDialog(mainWindow, { title: titulo || 'Escolher pasta', properties: ['openDirectory'] });
  return r.canceled || !r.filePaths.length ? { cancelado: true } : { ok: true, pasta: r.filePaths[0] };
});
ipcMain.handle('integra:pedir', (_evt, { comp, ids }) => _adm(() => integra.pedir(comp, ids)));
ipcMain.handle('integra:mitEstado', () => _adm(async () => integra.mitEstado()));
ipcMain.handle('integra:mitSalvarResp', (_evt, d) => _adm(() => integra.mitSalvarResp(d || {})));

ipcMain.handle('integra:abrirPasta', (_evt, pasta) => {
  if (!pasta || !fs.existsSync(pasta)) return { error: 'Essa pasta não está acessível neste computador.' };
  shell.openPath(pasta); return { ok: true };
});

// Importar CNPJs (só Admin): escolhe o arquivo, o Python lê a lista e o fechamento.js casa com as empresas cadastradas.
ipcMain.handle('fech:importarCnpjs', async () => {
  if (sessionRole !== 'admin') return { error: 'Só o Admin importa CNPJs.' };
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Lista de empresas com CNPJ', properties: ['openFile'],
    filters: [{ name: 'Relatório do Domínio, planilha ou texto', extensions: ['pdf', 'xlsx', 'xlsm', 'csv', 'txt'] }] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  const out = path.join(os.tmpdir(), `fc_lista_${Date.now()}.json`);
  try {
    await runFiscal(['lista-cnpjs', '--entrada', r.filePaths[0], '--json', out], out);
    const lido = JSON.parse(fs.readFileSync(out, 'utf-8'));
    if (!lido.ok) return { error: lido.erro };
    const previa = await fechamento.previaCnpjs(lido.empresas);
    return { ok: true, arquivo: path.basename(r.filePaths[0]), ...previa };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { fs.rm(out, { force: true }, () => {}); }
});
ipcMain.handle('fech:aplicarCnpjs', (_evt, pares) => _fech(() => fechamento.aplicarCnpjs(pares)));

ipcMain.handle('fech:cnpj', (_evt, cnpj) => _fech(async () => {
  const dig = String(cnpj || '').replace(/\D/g, '');
  if (dig.length !== 14) return { error: 'CNPJ inválido.' };
  const api = await _consultaCnpjApi(dig);
  if (!api) return { error: 'CNPJ não encontrado na Receita (ou consulta fora do ar).' };
  return { ok: true, nome: api.razao_social || api.nome || '' };
}));

ipcMain.handle('admin:usuariosListar', () => _adm(() => auth.listarUsuarios()));
ipcMain.handle('admin:usuarioCadastrar', (_evt, dados) => _adm(() => auth.cadastrarUsuario(dados || {})));
ipcMain.handle('admin:usuarioAlterar', (_evt, { uid, ...mud } = {}) => _adm(() => auth.alterarUsuario(uid, mud)));
ipcMain.handle('admin:usuarioNovaSenha', (_evt, uid) => _adm(() => auth.novaSenhaProvisoria(uid)));
ipcMain.handle('admin:usuarioRedefinir', (_evt, email) => _adm(async () => {
  const r = await auth.redefinirSenha(email); if (!r.ok) throw new Error(r.erro); return {};
}));
ipcMain.handle('admin:conviteCancelar', (_evt, email) => _adm(() => auth.cancelarConvite(email)));

ipcMain.handle('balancete:pick', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar balancete (PDF do Domínio)',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
    properties: ['openFile'],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, path: res.filePaths[0] };
});

ipcMain.handle('balancete:pickMultiple', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar vários balancetes (PDF do Domínio)',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
    properties: ['openFile', 'multiSelections'],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, paths: res.filePaths };
});

// ---------------------------------------------------------------------------
// IPC: Conferência de Balancetes em Lote — processa cada PDF com o MESMO
// núcleo do import individual (um de cada vez, reaproveitando runCore), e no
// final monta o painel consolidado via balancete_core.py --lote.
// ---------------------------------------------------------------------------
ipcMain.handle('balancete:processLote', async (_evt, pdfPaths) => {
  const { cmd } = pythonCore();
  if (app.isPackaged && !fs.existsSync(cmd)) {
    return { error: 'Núcleo não encontrado:\n' + cmd };
  }
  const resultados = [];
  const udir = app.getPath('userData');
  const configured = cloud.isCloudReady();
  for (const pdf of pdfPaths) {
    const jsonOut = path.join(os.tmpdir(), `fiscocont_lote_${Date.now()}_${resultados.length}.json`);
    try {
      const r = await runCore([pdf, '--json', jsonOut], jsonOut, 'json');
      let raw = (r && r.file) ? r.file : null;
      if (!raw && fs.existsSync(jsonOut)) raw = fs.readFileSync(jsonOut, 'utf-8');
      if (!raw) throw new Error('O núcleo não retornou dados.');
      const data = JSON.parse(raw);
      resultados.push({ arquivo: pdf, dados: data, erro: null });
      // sincroniza cada um com a nuvem, sem bloquear o lote (mesmo padrão do import individual)
      if (configured) {
        cloud.syncBalancete(udir, data, path.basename(pdf)).catch(() => {});
      }
    } catch (e) {
      resultados.push({ arquivo: pdf, dados: null, erro: String(e.message || e) });
    } finally {
      fs.unlink(jsonOut, () => {});
    }
  }

  const entradaTmp = path.join(os.tmpdir(), `fc_lote_entrada_${Date.now()}.json`);
  const htmlTmp = path.join(os.tmpdir(), `fc_lote_html_${Date.now()}.html`);
  try {
    fs.writeFileSync(entradaTmp, JSON.stringify(resultados));
    await runCore(['--lote', '--entrada', entradaTmp, '--html', htmlTmp], htmlTmp, 'exists');
    const html = fs.readFileSync(htmlTmp, 'utf-8');
    return { ok: true, html, total: resultados.length, falhas: resultados.filter((r) => !r.dados).length };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(entradaTmp, () => {});
    fs.unlink(htmlTmp, () => {});
  }
});

// ---------------------------------------------------------------------------
// IPC: processar o PDF (PDF -> JSON)
// ---------------------------------------------------------------------------
ipcMain.handle('balancete:process', async (_evt, pdf) => {
  if (!pdf || !fs.existsSync(pdf)) return { error: 'Arquivo não encontrado: ' + pdf };

  // verificação prévia do núcleo (empacotado)
  const { cmd } = pythonCore();
  if (app.isPackaged && !fs.existsSync(cmd)) {
    return { error: 'Núcleo não encontrado:\n' + cmd + '\nO instalador pode não ter incluído o balancete_core.exe (etapa do PyInstaller no build).' };
  }

  const jsonOut = path.join(os.tmpdir(), `fiscocont_${Date.now()}.json`);
  try {
    const r = await runCore([pdf, '--json', jsonOut], jsonOut, 'json');
    let raw = (r && r.file) ? r.file : null;
    if (!raw && fs.existsSync(jsonOut)) raw = fs.readFileSync(jsonOut, 'utf-8');
    if (!raw && r && r.stdout && r.stdout.trim()) raw = r.stdout;
    if (!raw) throw new Error('O núcleo não retornou dados. Confira se o PDF é um balancete do Domínio.');
    const data = JSON.parse(raw);
    // Mantém o JSON já parseado em cache — telas sob demanda (Indicadores) reaproveitam
    // isso em vez de reabrir o PDF do zero (que é bem mais lento). Apaga o cache anterior.
    if (lastJsonPath) fs.unlink(lastJsonPath, () => {});
    lastJsonPath = fs.existsSync(jsonOut) ? jsonOut : null;
    lastPdfPath = pdf;

    // Sincroniza com a nuvem (não bloqueia a UI); avisa o renderer ao terminar.
    const udir = app.getPath('userData');
    const configured = cloud.isCloudReady();
    if (configured) {
      const statusPath = path.join(udir, 'nuvem-status.json');
      (async () => {
        try {
          const info = await cloud.syncBalancete(udir, data, path.basename(pdf));
          const st = { ok: true, empresa: info.empresa, periodo: info.periodo, bytes: info.bytes, quando: new Date().toISOString() };
          try { fs.writeFileSync(statusPath, JSON.stringify(st)); } catch (_) {}
          if (mainWindow) mainWindow.webContents.send('cloud:synced', st);
        } catch (e) {
          const st = { ok: false, error: String(e.message || e), quando: new Date().toISOString() };
          try { fs.writeFileSync(statusPath, JSON.stringify(st)); } catch (_) {}
          if (mainWindow) mainWindow.webContents.send('cloud:synced', st);
        }
      })();
    }
    return { data, arquivo: path.basename(pdf), cloud: { configured } };
  } catch (e) {
    const msg = '[núcleo: ' + cmd + ']\n' + String(e.message || e);
    try { fs.writeFileSync(path.join(app.getPath('userData'), 'ultimo-erro.log'), msg); } catch (_) {}
    return { error: msg };
  }
});

ipcMain.handle('cloud:status', () => {
  return { configured: cloud.isCloudReady(), projectId: cloud.projectIdPublic() };
});

ipcMain.handle('cloud:lastSync', () => {
  try { return JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), 'nuvem-status.json'), 'utf-8')); }
  catch (_) { return null; }
});

ipcMain.handle('cloud:setup', async () => {
  const pick = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione a credencial (conta de serviço) do Firebase',
    filters: [{ name: 'JSON', extensions: ['json'] }],
    properties: ['openFile'],
  });
  if (pick.canceled || !pick.filePaths[0]) return { canceled: true };
  try {
    const r = cloud.setup(app.getPath('userData'), pick.filePaths[0]);
    return { ok: true, projectId: r.projectId };
  } catch (e) {
    return { error: String(e.message || e) };
  }
});

// ---- Bloqueio remoto por máquina (licença) ----
ipcMain.handle('license:check', async () => {
  try { return await license.checkLicense(app.getPath('userData')); }
  catch (e) { return { configurado: true, status: 'offline', codigo: '', erro: String(e.message || e) }; }
});
ipcMain.handle('license:getRealtimeStatus', () => lastRealtimeLicenseStatus);

function _temaPath() {
  return path.join(app.getPath('userData'), 'tema.json');
}
ipcMain.handle('tema:get', () => {
  try { return JSON.parse(fs.readFileSync(_temaPath(), 'utf-8')).nome || 'padrao'; }
  catch (_) { return 'padrao'; }
});
ipcMain.handle('tema:set', (_evt, nome) => {
  try { fs.writeFileSync(_temaPath(), JSON.stringify({ nome })); return { ok: true }; }
  catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------
// Download de Documentos Fiscais (NFS-e via ADN) — certificados e
// pasta de destino ficam guardados aqui, fora da pasta do programa,
// pra sobreviver a atualizações de versão (mesmo lugar do tema.json).
// ---------------------------------------------------------------
function _certDir() {
  const dir = path.join(app.getPath('userData'), 'certificados');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return dir;
}
function _certIndexPath() {
  return path.join(_certDir(), 'index.json');
}
function _lerIndiceCert() {
  try { return JSON.parse(fs.readFileSync(_certIndexPath(), 'utf-8')); }
  catch (_) { return { empresas: [] }; }
}
function _salvarIndiceCert(indice) {
  fs.writeFileSync(_certIndexPath(), JSON.stringify(indice, null, 2));
}
function _configDownloadPath() {
  return path.join(app.getPath('userData'), 'download_documentos_config.json');
}

ipcMain.handle('fiscal:pickPfx', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar certificado digital', properties: ['openFile'],
    filters: [{ name: 'Certificado digital', extensions: ['pfx', 'p12'] }],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, path: res.filePaths[0] };
});

ipcMain.handle('fiscal:pickPfxLote', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar certificados digitais (pode marcar vários)', properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Certificado digital', extensions: ['pfx', 'p12'] }],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, paths: res.filePaths };
});

// Lê a propriedade "Comentários" (Details do Windows Explorer) de um
// arquivo via PowerShell — não é um campo de texto comum, é uma
// propriedade do próprio Windows (Shell.Application), só dá pra ler
// pedindo pro sistema operacional. O índice da coluna "Comentários"
// muda dependendo da versão/idioma do Windows, por isso a busca pelo
// NOME da coluna em vez de um número fixo.
function _lerComentarioArquivo(caminhoArquivo) {
  return new Promise((resolve) => {
    const pasta = path.dirname(caminhoArquivo);
    const nomeArquivo = path.basename(caminhoArquivo);
    const pastaPs = pasta.replace(/'/g, "''");
    const nomePs = nomeArquivo.replace(/'/g, "''");
    const script = [
      '$ErrorActionPreference = "SilentlyContinue"',
      '$shell = New-Object -ComObject Shell.Application',
      `$folder = $shell.Namespace('${pastaPs}')`,
      'if ($folder -eq $null) { Write-Output ""; exit }',
      '$indice = -1',
      'for ($i = 0; $i -lt 300; $i++) {',
      '  $nomeColuna = $folder.GetDetailsOf($folder.Items, $i)',
      '  if ($nomeColuna -eq "Comentários" -or $nomeColuna -eq "Comments") { $indice = $i; break }',
      '}',
      'if ($indice -eq -1) { Write-Output ""; exit }',
      `$item = $folder.ParseName('${nomePs}')`,
      'if ($item -eq $null) { Write-Output ""; exit }',
      'Write-Output $folder.GetDetailsOf($item, $indice)',
    ].join('; ');
    let saida = '';
    try {
      const ps = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { windowsHide: true });
      ps.stdout.on('data', (d) => { saida += d.toString(); });
      ps.on('close', () => resolve(saida.trim()));
      ps.on('error', () => resolve(''));
    } catch (_) { resolve(''); }
  });
}

// Tira do NOME do arquivo (ou de qualquer texto) as senhas mais prováveis, em
// ordem de probabilidade. Não decide sozinho: cada candidata é TESTADA no
// próprio certificado, e só a que abrir vale. Formatos que aparecem no
// escritório: "EMPRESA - Senha 123456.pfx", "EMPRESA - 123456 (1).pfx",
// "EMPRESA_LTDA05780184000173 Senha 25500750.pfx", "EMPRESA_1347...-abc123.pfx".
function _candidatasSenha(texto) {
  let base = String(texto || '').replace(/\.(pfx|p12)$/i, '');
  base = base.replace(/\s*\(\d+\)\s*$/, '')               // "(1)" de download repetido
             .replace(/[\s_-]*c[óo]pia(\s+de.*)?$/i, '')  // "- Cópia"
             .trim();
  const cands = [];
  const add = (s) => {
    s = String(s || '').replace(/^[\s:=_-]+|[\s_-]+$/g, '');
    if (s.length < 3 || /\s/.test(s)) return;
    if (s.replace(/\D/g, '').length >= 14) return;         // é (ou contém) CNPJ, não senha
    if (!cands.includes(s)) cands.push(s);
  };
  const mSenha = base.match(/(?:^|[^A-Za-zÀ-ÿ])senha[\s:=_-]*([^\s]+)/i);   // 1) depois da palavra "senha"
  if (mSenha) { add(mSenha[1]); add(mSenha[1].split('_')[0]); }
  const h = base.lastIndexOf('-');                                            // 2) depois do último hífen
  if (h >= 0) add(base.slice(h + 1).replace(/^senha[\s:=_-]*/i, ''));
  const partes = base.split(/[\s_]+/).filter(Boolean);                        // 3) últimos pedaços
  for (let i = partes.length - 1; i >= Math.max(0, partes.length - 2); i--) add(partes[i]);
  return cands.slice(0, 6);
}

// Testa as candidatas de vários certificados de uma vez, num processo só.
async function _testarSenhasLote(itens) {
  const sufixo = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const entrada = path.join(os.tmpdir(), `fc_certs_in_${sufixo}.json`);
  const saida = path.join(os.tmpdir(), `fc_certs_out_${sufixo}.json`);
  try {
    fs.writeFileSync(entrada, JSON.stringify(itens), { encoding: 'utf-8', mode: 0o600 });
    await runFiscal(['ler-certificados-lote', entrada, '--json', saida], saida);
    return JSON.parse(fs.readFileSync(saida, 'utf-8'));
  } finally {
    [entrada, saida].forEach((f) => { try { fs.unlinkSync(f); } catch (_) {} });
  }
}

ipcMain.handle('fiscal:certImportarLote', async (_evt, caminhos) => {
  try {
    const resultados = caminhos.map((caminho) => {
      const nomeArquivo = path.basename(caminho);
      return { caminho, nomeArquivo, candidatas: _candidatasSenha(nomeArquivo), comentario: '', ok: false };
    });
    // 1ª rodada: senhas tiradas do NOME do arquivo — todos de uma vez
    const s1 = await _testarSenhasLote(resultados.map((r) => ({ caminho: r.caminho, candidatas: r.candidatas })));
    resultados.forEach((r, i) => {
      const x = s1[i] || {};
      if (x.ok) { r.ok = true; r.info = x.info; r.senhaTentativa = r.candidatas[x.indice_senha]; r.origem = 'nome'; }
      else r.detalhe = x.detalhe || '';
    });
    // 2ª rodada, só pros que não abriram: campo "Comentários" do Windows (plano B)
    const falhos = resultados.filter((r) => !r.ok);
    for (const r of falhos) {
      r.comentario = await _lerComentarioArquivo(r.caminho);
      r.candidatas = [...r.candidatas, ..._candidatasSenha(r.comentario)].filter((s, i, a) => a.indexOf(s) === i);
    }
    const comComentario = falhos.filter((r) => r.comentario);
    if (comComentario.length) {
      const s2 = await _testarSenhasLote(comComentario.map((r) => ({ caminho: r.caminho, candidatas: r.candidatas })));
      comComentario.forEach((r, i) => {
        const x = s2[i] || {};
        if (x.ok) { r.ok = true; r.info = x.info; r.senhaTentativa = r.candidatas[x.indice_senha]; r.origem = 'comentario'; }
      });
    }
    resultados.forEach((r) => {
      if (r.ok) return;
      r.senhaTentativa = r.candidatas[0] || '';
      r.qtdTentadas = r.candidatas.length;
      r.erro = r.candidatas.length
        ? 'Nenhuma das senhas que achei no nome do arquivo abriu o certificado — confira e digite abaixo.'
        : 'Não achei senha no nome do arquivo — digite abaixo.';
    });
    return { ok: true, resultados };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:certValidar', async (_evt, { pfxPath, senha }) => {
  const jsonTmp = path.join(os.tmpdir(), `fc_cert_val_${Date.now()}.json`);
  try {
    await runFiscal(['ler-certificado', pfxPath, '--senha', senha, '--json', jsonTmp], jsonTmp);
    const info = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    fs.unlink(jsonTmp, () => {});
    if (info.erro) return { error: info.erro };
    return { ok: true, info };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Filial: o certificado (e-CNPJ) da matriz baixa as NFS-e da filial pelo parâmetro cnpjConsulta do ADN,
// desde que a filial tenha a MESMA raiz (8 primeiros dígitos) do CNPJ do certificado.
function _cnpjValido(c) {
  if (!/^\d{14}$/.test(c) || /^(\d)\1+$/.test(c)) return false;
  const dv = (base) => {
    const pesos = base.length === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const r = base.split('').reduce((s, d, i) => s + Number(d) * pesos[i], 0) % 11;
    return r < 2 ? 0 : 11 - r;
  };
  return dv(c.slice(0, 12)) === Number(c[12]) && dv(c.slice(0, 13)) === Number(c[13]);
}
function _dadosFilial(cnpjCert, razao, cnpjFilialBruto) {
  const cnpjFilial = String(cnpjFilialBruto || '').replace(/\D/g, '');
  if (!_cnpjValido(cnpjFilial)) return { error: 'CNPJ da filial inválido — confira os 14 dígitos.' };
  if (cnpjFilial === cnpjCert) return { error: 'Esse é o próprio CNPJ do certificado — cadastre como Matriz.' };
  if (cnpjFilial.slice(0, 8) !== String(cnpjCert).slice(0, 8)) {
    return { error: `A filial precisa ter a mesma raiz do certificado (${String(cnpjCert).slice(0, 8)}…). Com outra raiz a Receita não libera as notas — use o certificado da própria empresa.` };
  }
  return { cnpj: cnpjFilial, razaoSocial: `${razao} - FILIAL ${cnpjFilial.slice(8, 12)}` };
}

ipcMain.handle('fiscal:certSalvar', async (_evt, { pfxPath, senha, info, tipo, cnpjFilial }) => {
  try {
    // achado real (Rafael, 04/11/2026): e-CPF ficava com documento vazio e o cadastro seguinte apagava o anterior
    const doc = String((info && info.cnpj) || '').replace(/\D/g, '');
    if (doc.length !== 14 && doc.length !== 11) return { error: 'Não consegui ler o CNPJ nem o CPF de dentro do certificado — confira se é um certificado A1 (e-CNPJ ou e-CPF) da ICP-Brasil.' };
    if (doc.length === 11 && tipo === 'filial') return { error: 'Certificado de pessoa física (e-CPF) não tem filial — cadastre como Matriz.' };
    let fil = null;
    if (tipo === 'filial') {
      fil = _dadosFilial(info.cnpj, info.razao_social, cnpjFilial);
      if (fil.error) return { error: fil.error };
    }
    // achado real (Rafael, 25/09/2026): certificado vencido não dá um erro
    // claro na hora de baixar — a Receita simplesmente rejeita a conexão
    // (aparece como falha de TLS, sem explicar o motivo real). Bloqueia
    // aqui, no cadastro, pra nem deixar salvar um certificado já vencido.
    if (info.validade && new Date(info.validade) < new Date()) {
      return { error: `Esse certificado está VENCIDO desde ${info.validade.split('-').reverse().join('/')} — não vai funcionar pra baixar nada. Peça um certificado válido antes de cadastrar.` };
    }
    const indice = _lerIndiceCert();
    const cnpjAlvo = fil ? fil.cnpj : info.cnpj;
    const id = `${cnpjAlvo}_${Date.now()}`;
    const pfxDestino = path.join(_certDir(), `${id}.pfx`);
    fs.copyFileSync(pfxPath, pfxDestino);
    if (safeStorage.isEncryptionAvailable()) {
      const senhaCifrada = safeStorage.encryptString(senha);
      fs.writeFileSync(path.join(_certDir(), `${id}.senha`), senhaCifrada);
    } else {
      return { error: 'A criptografia segura do sistema operacional não está disponível nesta máquina — não vou salvar a senha sem ela.' };
    }
    const antigos = indice.empresas.filter((e) => e.cnpj === cnpjAlvo && e.tipo !== 'procuracao').map((e) => e.id);
    indice.empresas = indice.empresas.filter((e) => e.cnpj !== cnpjAlvo); // recadastro substitui o antigo
    for (const e of indice.empresas) if (e.tipo === 'procuracao' && antigos.includes(e.procuradorId)) e.procuradorId = id;  // certificado do escritório renovado
    indice.empresas.push({
      id, cnpj: cnpjAlvo, razaoSocial: fil ? fil.razaoSocial : info.razao_social, validade: info.validade,
      tipo: fil ? 'filial' : 'matriz', cnpjCert: info.cnpj,
      pfxArquivo: `${id}.pfx`, ultimoNsu: 0, ultimoDownload: null,
    });
    _salvarIndiceCert(indice);
    return { ok: true };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Recupera certificados de pessoa física (e-CPF) que versões anteriores apagaram por engano: o e-CPF era gravado com
// documento vazio, e o cadastro seguinte de outro e-CPF substituía o anterior. O arquivo .pfx e a senha cifrada do
// anterior continuavam na pasta de certificados (id "_<data>"), só a linha da lista sumia. Roda uma vez por abertura.
let _pfRecuperado = false;
async function _recuperarCertificadosPF() {
  if (_pfRecuperado) return; _pfRecuperado = true;
  try {
    const dir = _certDir(); const indice = _lerIndiceCert(); let mudou = false;
    const ler = async (arqPfx, id) => {
      const sp = path.join(dir, `${id}.senha`);
      if (!fs.existsSync(path.join(dir, arqPfx)) || !fs.existsSync(sp)) return null;
      let senha; try { senha = safeStorage.decryptString(fs.readFileSync(sp)); } catch (_) { return null; }
      const jsonTmp = path.join(os.tmpdir(), `fc_cert_rec_${Date.now()}_${Math.random().toString(36).slice(2, 7)}.json`);
      try {
        await runFiscal(['ler-certificado', path.join(dir, arqPfx), '--senha', senha, '--json', jsonTmp], jsonTmp);
        const info = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8')); fs.unlink(jsonTmp, () => {});
        return info && !info.erro ? info : null;
      } catch (_) { return null; }
    };
    for (const e of indice.empresas) {                      // linhas já gravadas sem documento
      if (e.cnpj || !e.pfxArquivo) continue;
      const info = await ler(e.pfxArquivo, e.id);
      if (info && info.cnpj) { e.cnpj = info.cnpj; e.cnpjCert = info.cnpj; mudou = true; }
    }
    const usados = new Set(indice.empresas.map((e) => e.pfxArquivo).filter(Boolean));
    for (const arq of fs.readdirSync(dir)) {                // e-CPF apagados da lista
      if (!/^_\d+\.pfx$/.test(arq) || usados.has(arq)) continue;
      const id = arq.slice(0, -4);
      const info = await ler(arq, id);
      if (!info || !info.cnpj || indice.empresas.some((e) => e.cnpj === info.cnpj)) continue;
      indice.empresas.push({ id, cnpj: info.cnpj, razaoSocial: info.razao_social, validade: info.validade, tipo: 'matriz',
        cnpjCert: info.cnpj, pfxArquivo: arq, ultimoNsu: 0, ultimoDownload: null, recuperadoEm: new Date().toISOString() });
      mudou = true;
    }
    if (mudou) _salvarIndiceCert(indice);
  } catch (_) {}
}

// App do celular: só nome, CNPJ e validade de cada certificado (nunca o arquivo nem a senha), para o alerta de vencimento.
// Procuração fica de fora: a validade ali é a do certificado do escritório, não a do cliente.
let _certNuvemEm = 0;
async function _certNuvem(indice) {
  if (Date.now() - _certNuvemEm < 10 * 60000) return;
  const db = auth.db(), f = auth.fsMod(); if (!db || !f) return;
  _certNuvemEm = Date.now();
  try {
    const em = new Date().toISOString();
    for (const e of indice.empresas) {
      const cnpj = String(e.cnpj || '').replace(/\D/g, '');
      if (e.tipo === 'procuracao' || cnpj.length !== 14 || !e.validade) continue;
      await f.setDoc(f.doc(db, 'certificados', cnpj), { nome: e.razaoSocial || '', validade: e.validade, tipo: e.tipo || 'matriz', em }, { merge: true });
    }
  } catch (_) { _certNuvemEm = 0; }
}

ipcMain.handle('fiscal:certListar', async () => {
  await _recuperarCertificadosPF();
  const indice = _lerIndiceCert();
  _certNuvem(indice);
  return indice.empresas.map((e) => {
    const pr = e.tipo === 'procuracao' ? indice.empresas.find((x) => x.id === e.procuradorId) : null;
    return {
      id: e.id, cnpj: e.cnpj, razaoSocial: e.razaoSocial, validade: pr ? pr.validade : e.validade,
      ultimoDownload: e.ultimoDownload, tipo: e.tipo || 'matriz', cnpjCert: pr ? (pr.cnpjCert || pr.cnpj) : (e.cnpjCert || e.cnpj),
      procuradorNome: pr ? pr.razaoSocial : (e.tipo === 'procuracao' ? '' : undefined),
    };
  });
});

// "+ Filial" numa empresa já cadastrada: reaproveita o certificado e a senha (já cifrada) da matriz.
ipcMain.handle('fiscal:certAddFilial', (_evt, { id, cnpjFilial }) => {
  try {
    const indice = _lerIndiceCert();
    const base = indice.empresas.find((e) => e.id === id);
    if (!base) return { error: 'Empresa não encontrada.' };
    const cnpjCert = base.cnpjCert || base.cnpj;
    const razaoBase = (base.razaoSocial || '').replace(/ - FILIAL \d{4}$/, '');
    const fil = _dadosFilial(cnpjCert, razaoBase, cnpjFilial);
    if (fil.error) return fil;
    const novoId = `${fil.cnpj}_${Date.now()}`;
    fs.copyFileSync(path.join(_certDir(), base.pfxArquivo), path.join(_certDir(), `${novoId}.pfx`));
    fs.copyFileSync(path.join(_certDir(), `${base.id}.senha`), path.join(_certDir(), `${novoId}.senha`));
    indice.empresas = indice.empresas.filter((e) => e.cnpj !== fil.cnpj);
    indice.empresas.push({
      id: novoId, cnpj: fil.cnpj, razaoSocial: fil.razaoSocial, validade: base.validade,
      tipo: 'filial', cnpjCert, pfxArquivo: `${novoId}.pfx`, ultimoNsu: 0, ultimoDownload: null,
    });
    _salvarIndiceCert(indice);
    return { ok: true, razaoSocial: fil.razaoSocial };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:certRemover', (_evt, id) => {
  try {
    const indice = _lerIndiceCert();
    const alvo = indice.empresas.find((e) => e.id === id);
    if (!alvo) return { error: 'Empresa não encontrada.' };
    const dependem = indice.empresas.filter((e) => e.tipo === 'procuracao' && e.procuradorId === id);
    if (dependem.length) return { error: `Este é o certificado do procurador de ${dependem.length} empresa(s) cadastrada(s) por procuração. Remova essas empresas antes, ou cadastre o certificado novo do escritório (as procurações passam para ele).` };
    for (const arq of [alvo.pfxArquivo, `${id}.senha`].filter(Boolean)) {
      const p = path.join(_certDir(), arq);
      if (fs.existsSync(p)) fs.unlinkSync(p);
    }
    indice.empresas = indice.empresas.filter((e) => e.id !== id);
    _salvarIndiceCert(indice);
    return { ok: true };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---- Por procuração (desde 01/11/2026 o Sistema Nacional da NFS-e aceita acesso às APIs em nome de terceiros):
// o certificado do escritório (e-CNPJ da Liddera, cadastrado como Matriz) consulta o ADN com cnpjConsulta = CNPJ do
// cliente. A procuração é outorgada pelo cliente no Portal de Serviços da Receita Federal; sem ela o ADN responde E2245.
function _credDe(indice, empresa) {
  let dono = empresa;
  if (empresa.tipo === 'procuracao') {
    dono = indice.empresas.find((e) => e.id === empresa.procuradorId);
    if (!dono) return { error: 'O certificado do escritório (procurador) desta empresa não está mais cadastrado. Cadastre o e-CNPJ do escritório e cadastre a procuração de novo.' };
  }
  if (dono.validade && new Date(dono.validade) < new Date()) {
    return { error: `O certificado ${empresa.tipo === 'procuracao' ? 'do escritório (procurador)' : 'dessa empresa'} está VENCIDO desde ${dono.validade.split('-').reverse().join('/')} — cadastre um certificado válido antes de baixar.`, vencido: true };
  }
  const senhaPath = path.join(_certDir(), `${dono.id}.senha`);
  if (!fs.existsSync(senhaPath)) return { error: 'Senha do certificado não encontrada — cadastre o certificado novamente.' };
  try { return { pfxPath: path.join(_certDir(), dono.pfxArquivo), senha: safeStorage.decryptString(fs.readFileSync(senhaPath)), dono }; }
  catch (_) { return { error: 'Não consegui ler a senha salva com segurança nesta máquina.' }; }
}
ipcMain.handle('fiscal:procProcuradores', () => {
  const indice = _lerIndiceCert();
  return indice.empresas.filter((e) => (e.tipo || 'matriz') === 'matriz')
    .map((e) => ({ id: e.id, cnpj: e.cnpj, razaoSocial: e.razaoSocial, validade: e.validade }));
});
async function _procTestar(procuradorId, cnpj) {
  const indice = _lerIndiceCert();
  const pr = indice.empresas.find((e) => e.id === procuradorId && (e.tipo || 'matriz') === 'matriz');
  if (!pr) return { error: 'Escolha o certificado do escritório (procurador).' };
  const dig = String(cnpj || '').replace(/\D/g, '');
  if (!_cnpjValido(dig)) return { error: 'CNPJ da empresa inválido — confira os 14 dígitos.' };
  if (dig.slice(0, 8) === String(pr.cnpj).slice(0, 8)) return { error: 'Esse CNPJ tem a mesma raiz do certificado do escritório — cadastre como Matriz ou Filial, sem procuração.' };
  const cred = _credDe(indice, pr);
  if (cred.error) return { error: cred.error };
  const jsonTmp = path.join(os.tmpdir(), `fc_proc_${Date.now()}.json`);
  try {
    await runFiscal(['testar-procuracao', cred.pfxPath, '--senha', cred.senha, '--cnpj-consulta', dig, '--json', jsonTmp], jsonTmp);
    const r = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    fs.unlink(jsonTmp, () => {});
    if (!r.ok) return { error: r.erro, codigo: r.codigo };
    return { ok: true, tipoConsulta: r.tipo_consulta, documentos: r.documentos };
  } catch (e) { return { error: String(e.message || e) }; }
}
ipcMain.handle('fiscal:procTestar', (_evt, { procuradorId, cnpj }) => _procTestar(procuradorId, cnpj));
ipcMain.handle('fiscal:procSalvar', async (_evt, { procuradorId, cnpj, razaoSocial }) => {
  try {
    const nome = String(razaoSocial || '').trim().replace(/\s+/g, ' ').toUpperCase();
    if (!nome) return { error: 'Informe a razão social da empresa.' };
    const t = await _procTestar(procuradorId, cnpj);           // só salva com a procuração confirmada pelo ADN
    if (t.error) return t;
    const dig = String(cnpj).replace(/\D/g, '');
    const indice = _lerIndiceCert();
    const pr = indice.empresas.find((e) => e.id === procuradorId);
    indice.empresas = indice.empresas.filter((e) => e.cnpj !== dig);
    indice.empresas.push({
      id: `${dig}_${Date.now()}`, cnpj: dig, razaoSocial: nome, tipo: 'procuracao', procuradorId,
      cnpjCert: pr.cnpj, pfxArquivo: null, validade: null, ultimoNsu: 0, ultimoDownload: null,
      procuracaoConfirmadaEm: new Date().toISOString(),
    });
    _salvarIndiceCert(indice);
    return { ok: true, tipoConsulta: t.tipoConsulta };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Pasta padrão da equipe pro Baixas DF-e — pasta compartilhada em nuvem
// (Google Drive compartilhado, mapeado como G:). Se existir no
// computador (drive mapeado/sincronizado), usa ela sozinho, sem pedir
// escolha manual; só libera escolher outra pasta se ela não for achada
// (ex.: computador sem esse drive mapeado ainda).
const PASTA_PADRAO_NFSE = 'G:\\Drives compartilhados\\Fiscal - Lucro Real\\00 - Arquivos FISCAL\\Notas Automáticas - FiscoCont';

ipcMain.handle('fiscal:pickPastaBase', async () => {
  const res = await dialog.showOpenDialog(mainWindow, { title: 'Escolher pasta onde salvar os documentos', properties: ['openDirectory', 'createDirectory'] });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  fs.writeFileSync(_configDownloadPath(), JSON.stringify({ pastaBase: res.filePaths[0] }));
  return { canceled: false, path: res.filePaths[0] };
});
ipcMain.handle('fiscal:pastaBaseGet', () => {
  try {
    const pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase;
    if (pasta) return pasta;
  } catch (_) {}
  try {
    if (fs.existsSync(PASTA_PADRAO_NFSE)) {
      fs.writeFileSync(_configDownloadPath(), JSON.stringify({ pastaBase: PASTA_PADRAO_NFSE }));
      return PASTA_PADRAO_NFSE;
    }
  } catch (_) {}
  return null;
});

// Pastas por mês de emissão (1.8.0+): <base>/<MM-AAAA>/<empresa>; antiga: <base>/<empresa>
function _temPastaEmpresa(pastaBase, razao) {
  try {
    if (fs.existsSync(path.join(pastaBase, razao))) return true;
    return fs.readdirSync(pastaBase).some((m) => /^(\d{2}-\d{4}|\d{4}-\d{2})$/.test(m) && fs.existsSync(path.join(pastaBase, m, razao)));
  } catch (_) { return false; }
}

async function _analisarNfseEmpresa(empresa, dataInicial, dataFinal, opcoes = {}) {
  if (!dataInicial || !dataFinal) return { error: 'Informe a Data inicial e a Data final para ver o painel.' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde os documentos são salvos primeiro.' };
  const pastaGeral = pastaBase;
  pastaBase = _nfseBase(empresa, pastaGeral);
  if (pastaBase !== pastaGeral) {
    await _hidratarCliente({ nome: empresa.razaoSocial, cnpj: empresa.cnpj }, pastaBase, _mesesEntre(dataInicial, dataFinal), empresa.razaoSocial);
    // baixado antes da pasta do cliente (ficou em Notas Automáticas): o painel continua lendo de lá
    if (!_mesesEntre(dataInicial, dataFinal).some((c) => fs.existsSync(path.join(pastaBase, `${c.slice(5, 7)}-${c.slice(0, 4)}`, empresa.razaoSocial)))) pastaBase = pastaGeral;
  }
  const pastaEmpresa = path.join(pastaBase, empresa.razaoSocial);
  if (!_temPastaEmpresa(pastaBase, empresa.razaoSocial)) {
    // no lote, empresa sem nenhuma nota baixada não é erro: simplesmente não teve notas no período
    if (opcoes.vazioSePastaAusente) return { ok: true, resumo: { total_notas: 0, qtd_canceladas: 0 }, painelHtml: '' };
    return { error: 'Ainda não tem nenhuma nota baixada dessa empresa nessa pasta.' };
  }

  const painelTmp = path.join(os.tmpdir(), `fc_nfse_painel_${Date.now()}.html`);
  const jsonTmp = path.join(os.tmpdir(), `fc_nfse_analise_${Date.now()}.json`);
  try {
    // achado real (Rafael, 26/09): a pasta acumula downloads de vários
    // meses ao longo do tempo — o painel tem que respeitar o período
    // escolhido na tela, não misturar tudo que já foi baixado algum dia.
    const args = ['analisar-nfse', pastaEmpresa, '--cnpj', empresa.cnpj, '--empresa', empresa.razaoSocial,
      '--pasta-base', pastaBase, '--painel-html', painelTmp, '--json', jsonTmp];
    if (dataInicial) args.push('--inicio', dataInicial);
    if (dataFinal) args.push('--fim', dataFinal);
    await runFiscal(args, jsonTmp);
    const resumo = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    const painelHtml = fs.readFileSync(painelTmp, 'utf-8');
    [painelTmp, jsonTmp].forEach((p) => fs.unlink(p, () => {}));
    _biRegistrar('nfse', resumo, { cnpj: empresa.cnpj, empresa: empresa.razaoSocial, comp: String(dataInicial || '').slice(0, 7) });
    return { ok: true, resumo, painelHtml };
  } catch (e) { return { error: String(e.message || e) }; }
}

ipcMain.handle('fiscal:nfseAnalise', async (_evt, { empresaId, dataInicial, dataFinal }) => {
  const indice = _lerIndiceCert();
  const empresa = indice.empresas.find((e) => e.id === empresaId);
  if (!empresa) return { error: 'Empresa não encontrada.' };
  return _analisarNfseEmpresa(empresa, dataInicial, dataFinal);
});

ipcMain.handle('fiscal:nfseExportarHtml', async (_evt, { html, tipo, empresaNome }) => {
  const nomeArquivo = { 'efd-contrib': 'Conferencia-EFD-Contribuicoes', 'efd-corrigir': 'Correcao-EFD-Contribuicoes', 'auditoria-am': 'Auditoria-ICMS-AM', 'evolucao': 'Evolucao-Tributaria', 'fech-sn': 'Fechamento-Simples-Nacional' }[tipo] || 'Painel-NFSe';
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar HTML', defaultPath: `${nomeArquivo}-${(empresaNome || '').replace(/[^\w-]+/g, '_')}.html`,
    filters: [{ name: 'HTML', extensions: ['html'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  try {
    fs.writeFileSync(save.filePath, html, 'utf-8');
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Baixa as NFS-e de UMA empresa no período. `tipo` distingue o que é motivo de PULAR a empresa
// (certificado vencido, senha ausente, pasta não escolhida) de uma falha na baixa em si — o lote usa isso.
async function _baixarNfseEmpresa(empresa, dataInicial, dataFinal, gerarPdf) {
  const cred = _credDe(_lerIndiceCert(), empresa);
  if (cred.error) return { error: cred.error, tipo: 'pulada' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde salvar os documentos antes de baixar.', tipo: 'pulada' };
  pastaBase = _nfseBase(empresa, pastaBase);      // empresa com pasta no drive: cópia de trabalho + zips na pasta do cliente

  const { senha, pfxPath } = cred;
  const jsonTmp = path.join(os.tmpdir(), `fc_nfse_${Date.now()}.json`);
  try {
    // achado real (Rafael, 25/09): a tela hoje só tem o modo "por período"
    // (escolhe data inicial/final) — não existe ainda um modo de
    // "sincronizar rápido". Usar o ultimoNsu como ponto de partida aqui
    // fazia a busca pular documentos mais antigos que o período pedido,
    // sempre que um download anterior já tinha avançado esse ponteiro —
    // exatamente o caso de uma empresa com serviço tomado meses atrás.
    // Por período, sempre busca desde o início (NSU 0); o ultimoNsu fica
    // guardado pra quando eu construir o modo "sincronizar" de verdade.
    const args = ['baixar-nfse', pfxPath, '--senha', senha, '--empresa', empresa.razaoSocial,
      '--cnpj', empresa.cnpj, '--pasta', pastaBase, '--inicio', dataInicial, '--fim', dataFinal,
      '--nsu', '0', '--json', jsonTmp];
    if (gerarPdf === false) args.push('--sem-pdf');
    if (empresa.tipo === 'filial' || empresa.tipo === 'procuracao') args.push('--cnpj-consulta', empresa.cnpj);
    await runFiscal(args, jsonTmp);
    const resultado = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    fs.unlink(jsonTmp, () => {});
    if (!resultado.erro) {
      const indice = _lerIndiceCert();           // relê: no lote o índice muda a cada empresa
      const alvo = indice.empresas.find((e) => e.id === empresa.id);
      if (alvo) {
        alvo.ultimoNsu = resultado.ultimo_nsu || alvo.ultimoNsu;
        alvo.ultimoDownload = new Date().toISOString();
        _salvarIndiceCert(indice);
      }
    }
    if (!resultado.erro) {
      try {
        const meses = _mesesEntre(dataInicial, dataFinal);
        const pub = await _publicarCliente({ nome: empresa.razaoSocial, cnpj: empresa.cnpj }, pastaBase, meses, empresa.razaoSocial);
        resultado.pastaCliente = Object.values(pub.destinos)[0] || '';
        resultado.semPastaCliente = !!pub.semPasta;
        if (pub.erros.length) resultado.avisoPastaCliente = pub.erros.join('; ');
      } catch (e) { resultado.avisoPastaCliente = String(e.message || e); }
    }
    return resultado.erro ? { error: resultado.erro, tipo: 'erro' } : { ok: true, resultado };
  } catch (e) { return { error: String(e.message || e), tipo: 'erro' }; }
}

// ---------------------------------------------------------------------------
// Consulta Manifestação NF-e (só consulta, nada é enviado à SEFAZ) — liberada para a equipe (2.1.25).
// Usa o certificado A1 da empresa destinatária cadastrado nas Baixas DF-e. Os resultados ficam guardados
// (manifestacao-cache.json) para não consultar a mesma chave de novo: a SEFAZ bloqueia consulta repetida.
// ---------------------------------------------------------------------------
const _MANIF_FINAIS = ['confirmada', 'desconhecida', 'nao_realizada'];
const _MANIF_CACHE_MIN = 60;
function _manifCachePath() { return path.join(app.getPath('userData'), 'manifestacao-cache.json'); }
function _manifCacheLer() { try { return JSON.parse(fs.readFileSync(_manifCachePath(), 'utf-8')); } catch (_) { return { itens: {}, nomes: {} }; } }
function _manifCacheGravar(c) {
  // guarda só os últimos 20 mil resultados
  const ent = Object.entries(c.itens || {});
  if (ent.length > 20000) c.itens = Object.fromEntries(ent.sort((a, b) => (b[1].em || '').localeCompare(a[1].em || '')).slice(0, 20000));
  try { fs.writeFileSync(_manifCachePath(), JSON.stringify(c)); } catch (_) {}
}
function _certDaEmpresa(empresa) {
  if (empresa.tipo === 'procuracao') return { error: 'Esta empresa está cadastrada por procuração (só NFS-e). Para a Consulta Manifestação NF-e, cadastre o certificado da própria empresa.' };
  if (empresa.validade && new Date(empresa.validade) < new Date()) {
    return { error: `O certificado dessa empresa está VENCIDO desde ${empresa.validade.split('-').reverse().join('/')}. Cadastre um certificado válido nas Baixas DF-e.` };
  }
  const senhaPath = path.join(_certDir(), `${empresa.id}.senha`);
  if (!fs.existsSync(senhaPath)) return { error: 'Senha do certificado não encontrada — cadastre a empresa novamente nas Baixas DF-e.' };
  try { return { pfxPath: path.join(_certDir(), empresa.pfxArquivo), senha: safeStorage.decryptString(fs.readFileSync(senhaPath)) }; }
  catch (_) { return { error: 'Não consegui ler a senha salva com segurança nesta máquina.' }; }
}
const MANIF_ATIVA = false;   // retirada temporariamente (2.1.27) — religar junto com o renderer/app.js
const _manifAdm = async (fn) => {
  if (!MANIF_ATIVA) return { error: 'A Consulta Manifestação NF-e está temporariamente indisponível.' };
  if (!sessionRole) return { error: 'Entre com o seu usuário para consultar.' };
  if (sessionLocked) return { error: 'Sessão travada: digite a senha para continuar.' };
  try { return { ok: true, ...(await fn()) }; } catch (e) { return { error: String((e && e.message) || e) }; }
};
ipcMain.handle('manif:empresas', () => _manifAdm(async () => ({
  empresas: (_lerIndiceCert().empresas || []).map((e) => ({
    id: e.id, nome: e.razaoSocial, cnpj: e.cnpj, validade: e.validade || '', vencido: !!(e.validade && new Date(e.validade) < new Date()),
  })),
})));
ipcMain.handle('manif:importarChaves', () => _manifAdm(async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Arquivo com as chaves de acesso', properties: ['openFile'],
    filters: [{ name: 'Texto ou planilha', extensions: ['txt', 'csv', 'xlsx', 'xlsm'] }] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  const saida = path.join(os.tmpdir(), `fc_manif_ch_${Date.now()}.json`);
  await runFiscal(['manifestacao-chaves', r.filePaths[0], '--json', saida], saida);
  const res = JSON.parse(fs.readFileSync(saida, 'utf-8')); fs.unlink(saida, () => {});
  if (res.erro) throw new Error(res.erro);
  return { chaves: res.chaves || [] };
}));
ipcMain.handle('manif:consultar', (_evt, { empresaId, chaves }) => _manifAdm(async () => {
  const empresa = (_lerIndiceCert().empresas || []).find((e) => e.id === empresaId);
  if (!empresa) throw new Error('Empresa não encontrada nas Baixas DF-e — cadastre o certificado dela primeiro.');
  const cert = _certDaEmpresa(empresa);
  if (cert.error) throw new Error(cert.error);
  const lista = [...new Set((chaves || []).map((c) => String(c).replace(/\D/g, '')).filter((c) => c.length === 44))].slice(0, 2000);
  if (!lista.length) throw new Error('Nenhuma chave válida para consultar.');
  const cache = _manifCacheLer();
  const agora = Date.now();
  const chaveCache = (c) => `${empresa.cnpj}|${c}`;
  const faltam = lista.filter((c) => {
    const h = cache.itens[chaveCache(c)];
    if (!h || !h.item || ['erro', 'nao_encontrada'].includes(h.item.situacao)) return true;
    const final = ['cancelada', 'denegada'].includes(h.item.situacao) || _MANIF_FINAIS.includes(h.item.manifestacao);
    return !final && (agora - new Date(h.em).getTime()) > _MANIF_CACHE_MIN * 60000;
  });
  if (faltam.length) {
    // em partes de 100 chaves: cada processo do núcleo tem limite de tempo
    const env = (d) => { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('manif:progresso', d); };
    const guardadas = lista.length - faltam.length;
    env({ feitas: 0, total: faltam.length, guardadas });
    for (let ini = 0; ini < faltam.length; ini += 100) {
      const parte = faltam.slice(ini, ini + 100);
      const tag = `${agora}_${ini}`;
      const entrada = path.join(os.tmpdir(), `fc_manif_in_${tag}.json`);
      const saida = path.join(os.tmpdir(), `fc_manif_out_${tag}.json`);
      const prog = path.join(os.tmpdir(), `fc_manif_prog_${tag}.json`);
      fs.writeFileSync(entrada, JSON.stringify(parte));
      const tm = setInterval(() => {
        try { const p = JSON.parse(fs.readFileSync(prog, 'utf-8')); env({ feitas: ini + p.feitas, total: faltam.length, guardadas }); } catch (_) {}
      }, 700);
      try {
        await runFiscal(['manifestacao', cert.pfxPath, '--senha', cert.senha, '--cnpj', empresa.cnpj, '--entrada', entrada, '--progresso', prog, '--json', saida], saida);
      } finally { clearInterval(tm); }
      const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
      for (const f of [entrada, saida, prog]) fs.unlink(f, () => {});
      if (res.erro) throw new Error(res.erro);
      const em = new Date().toISOString();
      for (const it of res.itens || []) cache.itens[chaveCache(it.chave)] = { item: it, em };
      _manifCacheGravar(cache);
    }
  }
  const itens = lista.map((c) => ({ ...(cache.itens[chaveCache(c)] || {}).item, chave: c, consultadoEm: (cache.itens[chaveCache(c)] || {}).em || '' }));
  // nome do emitente pelo CNPJ quando o Ambiente Nacional não devolveu o resumo
  cache.nomes = cache.nomes || {};
  for (const cnpj of [...new Set(itens.filter((i) => !i.emitente && i.cnpj_emit).map((i) => i.cnpj_emit))].slice(0, 60)) {
    if (!(cnpj in cache.nomes)) {
      const api = await _consultaCnpjApi(cnpj).catch(() => null);
      cache.nomes[cnpj] = api ? (api.razao_social || api.nome || '') : '';
    }
  }
  for (const i of itens) if (!i.emitente && cache.nomes[i.cnpj_emit]) i.emitente = cache.nomes[i.cnpj_emit];
  _manifCacheGravar(cache);
  return { empresa: { nome: empresa.razaoSocial, cnpj: empresa.cnpj, validade: empresa.validade || '' }, itens, consultadas: faltam.length, quando: new Date().toISOString() };
}));
ipcMain.handle('manif:exportar', (_evt, { formato, itens, titulo, html, nome }) => _manifAdm(async () => {
  const ext = formato === 'xlsx' ? 'xlsx' : 'html';
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar consulta de manifestação',
    defaultPath: `${(nome || 'Manifestacao_NFe').replace(/[\\/:*?"<>|]/g, '_')}.${ext}`,
    filters: [{ name: ext === 'xlsx' ? 'Planilha Excel' : 'Página HTML', extensions: [ext] }] });
  if (r.canceled || !r.filePath) return { cancelado: true };
  if (ext === 'html') { fs.writeFileSync(r.filePath, String(html || ''), 'utf-8'); }
  else {
    const entrada = path.join(os.tmpdir(), `fc_manif_x_${Date.now()}.json`);
    const saida = entrada + '.res.json';
    fs.writeFileSync(entrada, JSON.stringify(itens || []));
    await runFiscal(['manifestacao-xlsx', r.filePath, '--entrada', entrada, '--titulo', String(titulo || ''), '--json', saida], saida);
    const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
    for (const f of [entrada, saida]) fs.unlink(f, () => {});
    if (res.erro) throw new Error(res.erro);
  }
  shell.openPath(r.filePath);
  return { path: r.filePath };
}));

// ---------------------------------------------------------------------------
// Consulta NF-e por chave · XML e PDF (2.2.27) — Admin e quem tiver o módulo "fiscal-nfechave" liberado.
// Situação na SEFAZ autorizadora + XML pelo Ambiente Nacional (consulta por chave) com o certificado da empresa
// escolhida (cadastrado nas Baixas DF-e) + DANFE. "Ciência da operação" só é enviada se o Admin marcar a opção.
// Resultados guardados em nfe-chave-cache.json: nota já baixada, cancelada/denegada ou NFC-e não é consultada de novo
// (a SEFAZ bloqueia consulta repetida da mesma chave).
// ---------------------------------------------------------------------------
function _nfechCachePath() { return path.join(app.getPath('userData'), 'nfe-chave-cache.json'); }
function _nfechCacheLer() { try { return JSON.parse(fs.readFileSync(_nfechCachePath(), 'utf-8')); } catch (_) { return { itens: {} }; } }
function _nfechCacheGravar(c) {
  const ent = Object.entries(c.itens || {});
  if (ent.length > 20000) c.itens = Object.fromEntries(ent.sort((a, b) => (b[1].em || '').localeCompare(a[1].em || '')).slice(0, 20000));
  try { fs.writeFileSync(_nfechCachePath(), JSON.stringify(c)); } catch (_) {}
}
// não consulta de novo: XML já baixado, cancelada/denegada (não mudam mais), ou autorizada sem download possível consultada há menos de 12 h
const _nfechFinal = (it, em) => it && ((it.xml && fs.existsSync(it.xml)) || ['cancelada', 'denegada'].includes(it.situacao)
  || (it.situacao === 'autorizada' && it.modelo !== '55' && em && Date.now() - Date.parse(em) < 12 * 3600000));
ipcMain.handle('nfech:empresas', () => _mod('fiscal-nfechave')(async () => {
  let pasta = '';
  try { pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) {}
  return {
    pasta,
    empresas: (_lerIndiceCert().empresas || []).map((e) => ({
      id: e.id, nome: e.razaoSocial, cnpj: e.cnpj, tipo: e.tipo || 'matriz', validade: e.validade || '',
      vencido: !!(e.validade && new Date(e.validade) < new Date()),
    })).sort((a, b) => a.nome.localeCompare(b.nome)),
  };
}));
ipcMain.handle('nfech:importar', () => _mod('fiscal-nfechave')(async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Arquivo com as chaves de acesso (SPED, planilha, texto ou XML)', properties: ['openFile'],
    filters: [{ name: 'SPED, texto, planilha ou XML', extensions: ['txt', 'csv', 'xlsx', 'xlsm', 'xml'] }] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  const saida = path.join(os.tmpdir(), `fc_nfech_ch_${Date.now()}.json`);
  await runFiscal(['manifestacao-chaves', r.filePaths[0], '--json', saida], saida);
  const res = JSON.parse(fs.readFileSync(saida, 'utf-8')); fs.unlink(saida, () => {});
  if (res.erro) throw new Error(res.erro);
  // SPED: o CNPJ do registro 0000 diz de qual empresa é o arquivo
  let cnpjArquivo = '';
  try {
    const ini = fs.readFileSync(r.filePaths[0], 'latin1').slice(0, 2000);
    const l0 = (ini.match(/\|0000\|[^\r\n]*/) || [''])[0];
    cnpjArquivo = l0.split('|').find((x) => /^\d{14}$/.test(x)) || '';
  } catch (_) {}
  return { chaves: res.chaves || [], cnpjArquivo, arquivo: path.basename(r.filePaths[0]) };
}));
ipcMain.handle('nfech:consultar', (_evt, { empresaId, chaves, baixar, ciencia, pdf, forcar }) => _mod('fiscal-nfechave')(async () => {
  const indice = _lerIndiceCert();
  const empresa = (indice.empresas || []).find((e) => e.id === empresaId);
  if (!empresa) throw new Error('Escolha a empresa (certificado cadastrado nas Baixas DF-e).');
  if (empresa.tipo === 'procuracao') throw new Error('Esta empresa está cadastrada por procuração (vale só para NFS-e). Para NF-e, cadastre o certificado da própria empresa nas Baixas DF-e.');
  const cred = _credDe(indice, empresa);
  if (cred.error) throw new Error(cred.error);
  let pasta = '';
  try { pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) {}
  const lista = [...new Set((chaves || []).map((c) => String(c).replace(/\D/g, '')).filter((c) => c.length === 44))].slice(0, 1000);
  if (!lista.length) throw new Error('Nenhuma chave válida para consultar.');
  const cache = _nfechCacheLer();
  const ck = (c) => `${empresa.cnpj}|${c}`;
  const faltam = forcar ? lista : lista.filter((c) => { const h = cache.itens[ck(c)]; return !(h && _nfechFinal(h.item, h.em)); });
  const env = (d) => { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('nfech:progresso', d); };
  const guardadas = lista.length - faltam.length;
  env({ feitas: 0, total: faltam.length, guardadas });
  for (let ini = 0; ini < faltam.length; ini += 50) {
    const parte = faltam.slice(ini, ini + 50);
    const tag = `${Date.now()}_${ini}`;
    const entrada = path.join(os.tmpdir(), `fc_nfech_in_${tag}.json`);
    const saida = path.join(os.tmpdir(), `fc_nfech_out_${tag}.json`);
    const prog = path.join(os.tmpdir(), `fc_nfech_prog_${tag}.json`);
    fs.writeFileSync(entrada, JSON.stringify({ chaves: parte, cnpj: empresa.cnpj, empresa: empresa.razaoSocial, pasta,
      baixar: baixar !== false, ciencia: !!ciencia, pdf: pdf !== false }));
    const tm = setInterval(() => {
      try { const p = JSON.parse(fs.readFileSync(prog, 'utf-8')); env({ feitas: ini + p.feitas, total: faltam.length, guardadas }); } catch (_) {}
    }, 700);
    try {
      await runFiscal(['nfe-chave', cred.pfxPath, '--senha', cred.senha, '--entrada', entrada, '--progresso', prog, '--json', saida], saida);
    } finally { clearInterval(tm); }
    const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
    for (const f of [entrada, saida, prog]) fs.unlink(f, () => {});
    if (res.erro) throw new Error(res.erro);
    const em = new Date().toISOString();
    for (const it of res.itens || []) cache.itens[ck(it.chave)] = { item: it, em };
    _nfechCacheGravar(cache);
  }
  const itens = lista.map((c) => { const h = cache.itens[ck(c)] || {}; return { ...h.item, chave: c, consultadoEm: h.em || '', guardada: !faltam.includes(c) }; });
  // nome do emitente pelo CNPJ quando a SEFAZ não devolveu
  cache.nomes = cache.nomes || {};
  for (const cnpj of [...new Set(itens.filter((i) => !i.emitente && i.cnpj_emit).map((i) => i.cnpj_emit))].slice(0, 60)) {
    if (!(cnpj in cache.nomes)) {
      const api = await _consultaCnpjApi(cnpj).catch(() => null);
      cache.nomes[cnpj] = api ? (api.razao_social || api.nome || '') : '';
    }
  }
  for (const i of itens) if (!i.emitente && cache.nomes[i.cnpj_emit]) i.emitente = cache.nomes[i.cnpj_emit];
  _nfechCacheGravar(cache);
  return { empresa: { nome: empresa.razaoSocial, cnpj: empresa.cnpj }, pasta, itens, consultadas: faltam.length, quando: new Date().toISOString() };
}));
// ---------------------------------------------------------------------------
// Baixas DF-e · NF-e e CT-e de ENTRADA (todas as empresas, Ambiente Nacional) e NF-e/NFC-e de SAÍDA (empresas de RO,
// DFe-Download da SEFIN) — quem tem o módulo Baixas DF-e. Posição da sequência (NSU) por empresa em dfe-nsu.json; resultado das
// saídas em dfe-ro.json (dfe_sefin.js). UF da empresa pelo cadastro público do CNPJ, guardada em dfe-uf.json.
// ---------------------------------------------------------------------------
const _dfeArq = (n) => path.join(app.getPath('userData'), n);
const _dfeLer = (n) => { try { return JSON.parse(fs.readFileSync(_dfeArq(n), 'utf-8')); } catch (_) { return {}; } };
const _dfeGrava = (n, d) => { try { fs.writeFileSync(_dfeArq(n), JSON.stringify(d, null, 1)); } catch (_) {} };
let _dfeRodando = false;
async function _dfeUf(cnpj, limite = 40) {
  const cache = _dfeLer('dfe-uf.json');
  if (cache[cnpj]) return cache[cnpj];
  if (limite <= 0) return '';
  const api = await _consultaCnpjApi(cnpj).catch(() => null);
  const uf = api ? String(api.uf || (api.estabelecimento && api.estabelecimento.estado && api.estabelecimento.estado.sigla) || '').toUpperCase() : '';
  if (uf) { cache[cnpj] = uf; _dfeGrava('dfe-uf.json', cache); }
  return uf;
}
function _dfeEmpresas() {
  return (_lerIndiceCert().empresas || []).filter((e) => (e.tipo || 'matriz') !== 'procuracao')
    .map((e) => ({ id: e.id, cnpj: e.cnpj, nome: e.razaoSocial, validade: e.validade || '', vencido: !!(e.validade && new Date(e.validade) < new Date()) }))
    .sort((a, b) => a.nome.localeCompare(b.nome));
}
// ---------------------------------------------------------------------------
// Pasta de cada empresa no drive (Fiscal - Lucro Presumido | Lucro Real | Simples Nacional \ <Empresa>\Relatórios\AAAA\mês)
// (pedido do Rafael, 17/11/2026). Empresa com pasta encontrada: os XML/PDF ficam numa cópia de trabalho deste computador
// e vão para a pasta do cliente em zips ("NFe Entradas 102026 - XML.zip" / "- PDF.zip"). Sem pasta: tudo como antes,
// na pasta escolhida nas Baixas DF-e, com aviso. O sistema nunca cria a pasta da empresa.
// ---------------------------------------------------------------------------
const pastaCliente = require('./pasta_cliente');
function _dfeTrabalho() { const d = path.join(app.getPath('userData'), 'DF-e trabalho'); fs.mkdirSync(d, { recursive: true }); return d; }
function _cliDe(e) { try { return pastaCliente.achar({ nome: e.nome || e.razaoSocial, cnpj: e.cnpj }); } catch (_) { return null; } }
function _dfeBaseDe(e, pasta) { return _cliDe(e) ? _dfeTrabalho() : pasta; }
const ROT_ZIP = { 'NF-e Entradas': 'NFe Entradas', 'NF-e Saídas': 'NFe Saidas', 'NFC-e Saídas': 'NFC-e Saidas', 'CT-e Entradas': 'CT-e Entradas', 'NFS-e': 'NFS-e' };
// zips do(s) mês(es) na pasta do cliente · base/<MM-AAAA>/<nomePasta>/<tipo>/{XML,PDF} · extras: [{copiar, para}]
async function _publicarCliente(e, base, meses, nomePasta, extras = []) {
  const cli = _cliDe(e);
  if (!cli) return { destinos: {}, erros: [], semPasta: true };
  const lista = [...extras], destinos = {};
  for (const comp of new Set(meses || [])) {
    if (!/^\d{4}-\d{2}$/.test(comp)) continue;
    const [a, m] = comp.split('-');
    const dEmp = path.join(base, `${m}-${a}`, nomePasta);
    if (!fs.existsSync(dEmp)) continue;
    const dCli = pastaCliente.pastaMes(cli.dir, a, m, true);
    if (!dCli) continue;
    destinos[comp] = dCli;
    for (const [sub, rot] of Object.entries(ROT_ZIP)) {
      for (const k of ['XML', 'PDF']) {
        const o = path.join(dEmp, sub, k);
        if (fs.existsSync(o)) lista.push({ origem: o, zip: path.join(dCli, `${rot} ${m}${a} - ${k}.zip`) });
      }
    }
  }
  if (!lista.length) return { destinos, erros: [] };
  const tag = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  const ent = path.join(os.tmpdir(), `fc_pub_${tag}.json`), out = path.join(os.tmpdir(), `fc_pub_out_${tag}.json`);
  fs.writeFileSync(ent, JSON.stringify(lista));
  try { await runFiscal(['publicar-zip', '--entrada', ent, '--json', out], out); } finally { fs.unlink(ent, () => {}); }
  let r = {};
  try { r = JSON.parse(fs.readFileSync(out, 'utf-8')); } catch (_) {}
  fs.unlink(out, () => {});
  return { destinos, erros: r.erros || (r.erro ? [r.erro] : []) };
}

// o contrário: traz para a cópia de trabalho deste computador o que já está nos zips da pasta do cliente (baixado em
// outro computador), antes do painel da NFS-e e do Relatório DF-e
async function _hidratarCliente(e, base, meses, nomePasta) {
  const cli = _cliDe(e);
  if (!cli) return 0;
  const lista = [];
  for (const comp of new Set(meses || [])) {
    if (!/^\d{4}-\d{2}$/.test(comp)) continue;
    const [a, m] = comp.split('-');
    const dCli = pastaCliente.pastaMes(cli.dir, a, m, false);
    if (!dCli || !fs.existsSync(dCli)) continue;
    for (const [sub, rot] of Object.entries(ROT_ZIP)) for (const k of ['XML', 'PDF']) {
      const z = path.join(dCli, `${rot} ${m}${a} - ${k}.zip`);
      if (fs.existsSync(z)) lista.push({ hidratar: z, destino: path.join(base, `${m}-${a}`, nomePasta, sub, k) });
    }
  }
  if (!lista.length) return 0;
  const tag = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  const ent = path.join(os.tmpdir(), `fc_hid_${tag}.json`), out = path.join(os.tmpdir(), `fc_hid_out_${tag}.json`);
  fs.writeFileSync(ent, JSON.stringify(lista));
  try { await runFiscal(['publicar-zip', '--entrada', ent, '--json', out], out); } catch (_) { return 0; } finally { fs.unlink(ent, () => {}); }
  try { const r = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {}); return (r.feitos || []).reduce((s2, x) => s2 + (x.novos || 0), 0); } catch (_) { return 0; }
}
function _mesesEntre(ini, fim) {
  const out = [];
  if (!/^\d{4}-\d{2}/.test(ini || '') || !/^\d{4}-\d{2}/.test(fim || '')) return out;
  for (let d = new Date(`${ini.slice(0, 7)}-01T12:00:00`); d <= new Date(`${fim.slice(0, 10)}T12:00:00`) && out.length < 36; d.setMonth(d.getMonth() + 1)) out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  return out;
}
// NFS-e: empresa com pasta no drive usa a cópia de trabalho (os arquivos vão em zip para a pasta do cliente)
function _nfseBase(empresa, pastaBase) { return _cliDe({ nome: empresa.razaoSocial, cnpj: empresa.cnpj }) ? _dfeTrabalho() : pastaBase; }

// mesmo nome de pasta que o Python usa (nfe_chave._limpa_nome)
function _dfeNomePasta(nome) { return String(nome || '').replace(/[\\/:*?"<>|]+/g, ' ').trim().replace(/\.+$/, '').replace(/\s+/g, ' ').slice(0, 120) || 'Empresa'; }
ipcMain.handle('dfe:estado', (_evt, { competencia } = {}) => _mod('fiscal-downloads')(async () => {
  const lst = _dfeEmpresas();
  let busca = 15;
  const nsu = _dfeLer('dfe-nsu.json'), ro = dfeSefin.lerEstado(), rel = _dfeLer('dfe-rel.json');
  for (const e of lst) { e.uf = await _dfeUf(e.cnpj, busca); if (!_dfeLer('dfe-uf.json')[e.cnpj]) busca--; }
  return {
    pasta: (() => { try { return JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) { return ''; } })(),
    empresas: lst.map((e) => ({ ...e, entradas: ((nsu[e.cnpj] || {}).ultimo || {})[competencia] || null, saidas: (ro[e.cnpj] || {})[competencia] || null,
      relatorio: (() => { const r = (rel[e.cnpj] || {})[competencia]; return r && r.html && fs.existsSync(r.html) ? { quando: r.quando, pdfs: r.pdfs, pdfTotal: r.pdfTotal } : null; })(),
      cliente: (() => { const c = _cliDe(e); return c ? { pasta: c.nome, regime: c.regime } : null; })() })),
    drive: pastaCliente.disponivel(),
  };
}));
ipcMain.handle('dfe:entradas', (_evt, { ids, competencia, tipos, ciencia }) => _mod('fiscal-downloads')(async () => {
  if (_dfeRodando) throw new Error('Já existe uma busca em andamento.');
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(competencia || '')) throw new Error('Competência inválida.');
  let pasta = '';
  try { pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) {}
  if (!pasta) throw new Error('Escolha a pasta das Baixas DF-e primeiro.');
  const indice = _lerIndiceCert();
  const alvo = _dfeEmpresas().filter((e) => !ids || ids.includes(e.id));
  const env = (d) => { try { mainWindow && mainWindow.webContents.send('dfe:progresso', d); } catch (_) {} };
  const saida = [];
  _dfeRodando = true;
  try {
    for (const [n, e] of alvo.entries()) {
      env({ txt: `Entradas · ${e.nome} (${n + 1} de ${alvo.length}): consultando o Ambiente Nacional…` });
      const emp = (indice.empresas || []).find((x) => x.id === e.id);
      const cred = _credDe(indice, emp);
      if (cred.error) { saida.push({ cnpj: e.cnpj, nome: e.nome, erro: cred.error }); continue; }
      const uf = await _dfeUf(e.cnpj);
      const nsu = _dfeLer('dfe-nsu.json');
      const tag = `${Date.now()}_${n}`;
      const entrada = path.join(os.tmpdir(), `fc_dfe_in_${tag}.json`), out = path.join(os.tmpdir(), `fc_dfe_out_${tag}.json`);
      const base = _dfeBaseDe(e, pasta);
      fs.writeFileSync(entrada, JSON.stringify({ pfx: cred.pfxPath, senha: cred.senha, cnpj: e.cnpj, empresa: e.nome, uf, pasta: base,
        estado: (nsu[e.cnpj] || {}).estado || {}, tipos: tipos && tipos.length ? tipos : ['nfe', 'cte'], ciencia: sessionRole === 'admin' ? !!ciencia : true, competencia }));
      try {
        await runFiscal(['dfe-notas', '--entrada', entrada, '--json', out], out);
      } finally { fs.unlink(entrada, () => {}); }
      const r = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
      if (r.erro) { saida.push({ cnpj: e.cnpj, nome: e.nome, erro: r.erro }); continue; }
      // pasta do cliente: zips de cada mês que recebeu nota
      const mesesPub = new Set([competencia]);
      for (const x of Object.values(r.res || {})) if (x) Object.keys(x.meses || {}).forEach((m) => mesesPub.add(m));
      const pub = base !== pasta ? await _publicarCliente(e, base, [...mesesPub], _dfeNomePasta(e.nome)) : null;
      const resumo = {};
      for (const [t, x] of Object.entries(r.res || {})) {
        if (!x) continue;
        // pasta do mês escolhido (as notas ficam na pasta do mês de emissão; a sequência da SEFAZ traz todos os meses)
        const [ca, cm] = competencia.split('-');
        const pastaMes = pub && pub.destinos[competencia] ? pub.destinos[competencia] : path.join(base, `${cm}-${ca}`, _dfeNomePasta(e.nome), t === 'cte' ? 'CT-e Entradas' : 'NF-e Entradas', 'XML');
        resumo[t] = { baixadas: x.baixadas.length, mes: x.mes, meses: x.meses || {}, resumos: x.resumos.length, canceladas: x.canceladas.length, ciencias: x.ciencias,
          ciencia_erros: x.ciencia_erros.length, aviso: x.aviso, erro: x.erro, quando: new Date().toISOString(), cliente: !!pub, pubErros: pub ? pub.erros : [],
          pasta: fs.existsSync(pastaMes) ? pastaMes : (x.baixadas.length ? path.dirname(x.baixadas[x.baixadas.length - 1].xml) : '') };
      }
      const novo = _dfeLer('dfe-nsu.json');
      novo[e.cnpj] = { ...(novo[e.cnpj] || {}), estado: r.estado, ultimo: { ...((novo[e.cnpj] || {}).ultimo || {}), [competencia]: resumo } };
      _dfeGrava('dfe-nsu.json', novo);
      saida.push({ cnpj: e.cnpj, nome: e.nome, uf, ...resumo });
    }
    // Segunda opção (2.4.5): o Ambiente Nacional mandou aguardar 1 hora → empresas de RO pegam as NF-e recebidas do mês no
    // arquivo de NF-e do DFe-Download da SEFIN (o mesmo das saídas, que traz emitidas e recebidas; e-CNPJ do Windows e o
    // código digitado pela pessoa). Se o arquivo do mês já foi baixado nas saídas, as entradas dele já estão na pasta.
    const bloq = saida.filter((x) => x.uf === 'RO' && x.nfe && !x.nfe.erro && /libera nova consulta|aguardar/.test(x.nfe.aviso || ''));
    if (bloq.length) {
      env({ txt: `Entradas · o Ambiente Nacional pediu para aguardar 1 hora: buscando as NF-e recebidas pelo DFe-Download da SEFIN…` });
      let rs = { empresas: [] };
      try { rs = await dfeSefin.baixar(bloq.map((x) => ({ cnpj: x.cnpj, nome: x.nome })), competencia, ['nfe']); }
      catch (err) { rs = { empresas: bloq.map((x) => ({ cnpj: x.cnpj, nfe: { status: 'erro', msg: String(err.message || err) } })) }; }
      const novo = _dfeLer('dfe-nsu.json');
      for (const y of rs.empresas || []) {
        const x = saida.find((z) => z.cnpj === y.cnpj); const r2 = y.nfe || (y.parado ? { status: 'cancelado', msg: 'a busca foi interrompida.' } : null);
        if (!x || !r2) continue;
        const base = _dfeBaseDe(x, pasta);
        let pastaEnt = (r2.entradas || {}).pasta || '';
        if (base !== pasta && ['baixado', 'parcial'].includes(r2.status)) {
          const pub = await _publicarCliente(x, base, [competencia], _dfeNomePasta(x.nome));
          if (pub.destinos[competencia]) pastaEnt = pub.destinos[competencia];
        }
        r2.pasta = pastaEnt;
        const en = r2.entradas || {};
        const msg2 = ['baixado', 'parcial'].includes(r2.status) && !en.qtd ? 'o arquivo de NF-e da SEFIN não trouxe notas recebidas por esta empresa.' : (r2.msg === 'já baixado antes' ? '' : r2.msg || '');
        x.nfe = { ...x.nfe, sefin: { status: r2.status, msg: msg2, qtd: en.qtd || 0, valor: en.valor || 0, canceladas: en.canceladas || 0, quando: new Date().toISOString() } };
        if (r2.pasta) x.nfe.pasta = r2.pasta;
        const ult = ((novo[x.cnpj] || {}).ultimo || {})[competencia];
        if (ult && ult.nfe) { ult.nfe.sefin = x.nfe.sefin; if (r2.pasta) ult.nfe.pasta = r2.pasta; }
      }
      _dfeGrava('dfe-nsu.json', novo);
    }
  } finally { _dfeRodando = false; env({ txt: '' }); }
  return { empresas: saida };
}));
ipcMain.handle('dfe:saidas', (_evt, { ids, competencia, tipos }) => _mod('fiscal-downloads')(async () => {
  const alvo = [];
  for (const e of _dfeEmpresas().filter((x) => !ids || ids.includes(x.id))) if ((await _dfeUf(e.cnpj)) === 'RO') alvo.push({ cnpj: e.cnpj, nome: e.nome });
  if (!alvo.length) throw new Error('Nenhuma empresa de Rondônia na seleção: as saídas pelo DFe-Download são só para empresas de RO.');
  const r = await dfeSefin.baixar(alvo, competencia, tipos && tipos.length ? tipos : ['nfe', 'nfce']);
  const pasta = (() => { try { return JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) { return ''; } })();
  for (const x of r.empresas || []) {
    const base = _dfeBaseDe(x, pasta);
    if (base === pasta) continue;
    const pub = await _publicarCliente(x, base, [competencia], _dfeNomePasta(x.nome));
    const dCli = pub.destinos[competencia];
    if (dCli) {                                   // "Abrir pasta" leva à pasta do cliente
      const est = dfeSefin.lerEstado();
      const s2 = ((est[x.cnpj] || {})[competencia]) || {};
      for (const t of Object.keys(s2)) if (s2[t] && typeof s2[t] === 'object') s2[t].pasta = dCli;
      dfeSefin.gravaEstado(est);
    }
  }
  return r;
}));
// Relatório DF-e (HTML com painel) e PDF das NF-e/CT-e: gerados a partir dos XMLs já baixados e salvos na pasta da empresa
ipcMain.handle('dfe:relatorio', (_evt, { ids, competencias, pdf } = {}) => _mod('fiscal-downloads')(async () => {
  let pasta = '';
  try { pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) {}
  if (!pasta) throw new Error('Escolha a pasta das Baixas DF-e primeiro.');
  const comps = (competencias || []).filter((c) => /^\d{4}-(0[1-9]|1[0-2])$/.test(c));
  if (!comps.length) throw new Error('Competência inválida.');
  const alvo = _dfeEmpresas().filter((e) => !ids || ids.includes(e.id));
  const env = (d) => { try { mainWindow && mainWindow.webContents.send('dfe:progresso', d); } catch (_) {} };
  const saida = [];
  try {
    for (const [n, e] of alvo.entries()) {
      for (const c of comps) {
        env({ txt: `Relatório${pdf ? ' e PDFs' : ''} · ${e.nome} (${n + 1} de ${alvo.length}) · ${c.split('-').reverse().join('/')}…` });
        const out = path.join(os.tmpdir(), `fc_dfe_rel_${Date.now()}_${n}.json`);
        const base = _dfeBaseDe(e, pasta);
        const [ra, rm] = c.split('-');
        const cli = base !== pasta ? _cliDe(e) : null;
        const dCli = cli ? pastaCliente.pastaMes(cli.dir, ra, rm, true) : null;
        const pub = dCli ? path.join(dCli, `Relatório DF-e ${rm}${ra}.html`) : '';
        if (dCli) await _hidratarCliente(e, base, [c], _dfeNomePasta(e.nome));
        await runFiscal(['dfe-relatorio', '--pasta', base, '--empresa', e.nome, '--cnpj', e.cnpj, '--competencia', c, '--pdf', pdf ? '1' : '0',
          ...(pub ? ['--publico', pub] : []), '--json', out], out);
        const r = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
        if (r.erro) { saida.push({ id: e.id, nome: e.nome, competencia: c, erro: r.erro }); continue; }
        const pdfTotal = ['nfe-e', 'cte-e', 'nfe-s'].reduce((s, k) => s + (((r.resumo || {})[k] || {}).qtd || 0), 0);
        const rel = _dfeLer('dfe-rel.json');
        const zp = dCli ? await _publicarCliente(e, base, [c], _dfeNomePasta(e.nome)) : null;
        rel[e.cnpj] = { ...(rel[e.cnpj] || {}), [c]: { html: r.html, publico: r.publico || '', pastaCliente: dCli || '', quando: new Date().toISOString(), pdfs: r.pdfs, pdfTotal, pdfErros: r.pdf_erros } };
        if (zp && zp.erros.length) saida.push({ id: e.id, nome: e.nome, competencia: c, erro: `zips na pasta do cliente: ${zp.erros.join('; ')}` });
        _dfeGrava('dfe-rel.json', rel);
        saida.push({ id: e.id, nome: e.nome, competencia: c, ok: true, pdfs: r.pdfs, pdf_erros: r.pdf_erros });
      }
    }
  } finally { env({ txt: '' }); }
  return { empresas: saida };
}));
// relatório para o CLIENTE só com os tipos escolhidos (ex.: só NFC-e): HTML + PDF na pasta do cliente (Relatórios › AAAA › MM)
const DFE_TIPOS_REL = { 'nfe-e': 'NF-e Entradas', 'cte-e': 'CT-e Entradas', 'nfe-s': 'NF-e Saídas', 'nfce-s': 'NFC-e Saídas' };
ipcMain.handle('dfe:relatorioCliente', (_evt, { id, competencia, tipos } = {}) => _mod('fiscal-downloads')(async () => {
  let pasta = '';
  try { pasta = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || ''; } catch (_) {}
  if (!pasta) throw new Error('Escolha a pasta das Baixas DF-e primeiro.');
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(competencia || '')) throw new Error('Competência inválida.');
  const t = (tipos || []).filter((x) => DFE_TIPOS_REL[x]);
  if (!t.length) throw new Error('Marque pelo menos um tipo de documento.');
  const e = _dfeEmpresas().find((x) => x.id === id);
  if (!e) throw new Error('Empresa não encontrada.');
  const base = _dfeBaseDe(e, pasta);
  const [ra, rm] = competencia.split('-');
  const cli = base !== pasta ? _cliDe(e) : null;
  const dCli = cli ? pastaCliente.pastaMes(cli.dir, ra, rm, true) : null;
  if (dCli) await _hidratarCliente(e, base, [competencia], _dfeNomePasta(e.nome));
  const destDir = dCli || path.join(base, `${rm}-${ra}`, _dfeNomePasta(e.nome));
  const rot = t.length === 4 ? 'DF-e' : t.map((x) => DFE_TIPOS_REL[x]).join(' e ');
  const nomeArq = `Relatório ${rot} ${rm}${ra} - ${_dfeNomePasta(e.nome)}`.replace(/[\\/:*?"<>|]+/g, ' ').slice(0, 150);
  const html = path.join(destDir, `${nomeArq}.html`);
  const out = path.join(os.tmpdir(), `fc_dfe_relc_${Date.now()}.json`);
  await runFiscal(['dfe-relatorio', '--pasta', base, '--empresa', e.nome, '--cnpj', e.cnpj, '--competencia', competencia, '--pdf', '0',
    '--tipos', t.join(','), '--so-publico', '1', '--publico', html, '--json', out], out);
  const r = JSON.parse(fs.readFileSync(out, 'utf-8')); fs.unlink(out, () => {});
  if (r.erro) throw new Error(r.erro);
  // PDF do mesmo relatório (para mandar por e-mail/WhatsApp): a página é aberta escondida e impressa depois dos gráficos
  let pdf = '';
  const w = new BrowserWindow({ show: false, width: 1400, height: 1000, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
  try {
    await w.loadFile(html);
    await new Promise((ok) => setTimeout(ok, 2500));
    const buf = await w.webContents.printToPDF({ landscape: true, printBackground: true, pageSize: 'A4', margins: { marginType: 'custom', top: 0.3, bottom: 0.3, left: 0.3, right: 0.3 } });
    pdf = path.join(destDir, `${nomeArq}.pdf`);
    fs.writeFileSync(pdf, buf);
  } catch (err) { pdf = ''; } finally { try { w.destroy(); } catch (_) {} }
  return { html, pdf, pasta: destDir, resumo: r.resumo || {} };
}));
ipcMain.handle('dfe:relatorioAbrir', (_evt, { id, competencia } = {}) => _mod('fiscal-downloads')(async () => {
  const e = _dfeEmpresas().find((x) => x.id === id);
  const r = e && (_dfeLer('dfe-rel.json')[e.cnpj] || {})[competencia];
  const alvo = r && r.publico && fs.existsSync(r.publico) ? r.publico : r && r.html;
  if (!alvo || !fs.existsSync(alvo)) throw new Error('O relatório deste mês ainda não foi gerado.');
  const erro = await shell.openPath(alvo);
  if (erro) throw new Error(erro);
  return {};
}));
ipcMain.handle('dfe:captcha', (_evt, { id, texto } = {}) => _mod('fiscal-downloads')(async () => dfeSefin.respostaCodigo(id, texto)));
ipcMain.handle('dfe:cancelar', () => _mod('fiscal-downloads')(async () => dfeSefin.cancelar()));
ipcMain.handle('dfe:abrir', (_evt, caminho) => _mod('fiscal-downloads')(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('Pasta não encontrada.');
  await shell.openPath(caminho);
  return {};
}));
ipcMain.handle('dfe:log', () => _mod('fiscal-downloads')(async () => { await shell.openPath(app.getPath('userData')); return {}; }));

// Eventos pelo Portal Nacional da NF-e (2.4.4): só as NF-e autorizadas que voltaram SEM eventos do serviço da SEFAZ.
// A pessoa marca o "Sou humano"; o resto (consulta completa com o e-CNPJ da empresa instalado no Windows) é escondido.
// Nota com eventos lidos não volta ao portal; nota que o portal mostrou sem eventos só volta depois de 24 h.
const nfePortal = require('./nfe_portal');
nfePortal.init({ userData: () => app.getPath('userData'), janelaPai: () => mainWindow });
const _nfechPortalPrecisa = (it) => it && it.modelo === '55' && it.situacao === 'autorizada' && !(it.eventos || []).length
  && !(it.portal && it.portal.em && !it.portal.erro && Date.now() - Date.parse(it.portal.em) < 24 * 3600000);
let _nfechPortalRodando = false;
ipcMain.handle('nfech:eventosPortal', (_evt, { empresaId, chaves }) => _mod('fiscal-nfechave')(async () => {
  if (_nfechPortalRodando) throw new Error('Os eventos já estão sendo consultados.');
  const empresa = (_lerIndiceCert().empresas || []).find((e) => e.id === empresaId);
  if (!empresa) throw new Error('Empresa não encontrada.');
  const cache = _nfechCacheLer();
  const ck = (c) => `${empresa.cnpj}|${c}`;
  const lista = [...new Set((chaves || []).map((c) => String(c).replace(/\D/g, '')))].filter((c) => _nfechPortalPrecisa((cache.itens[ck(c)] || {}).item));
  if (!lista.length) return { itens: [], semCert: false };
  const env = (d) => { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('nfech:progresso', { portal: true, ...d }); };
  _nfechPortalRodando = true;
  let res;
  try {
    res = await nfePortal.eventos(lista.map((c) => ({ chave: c, numero: cache.itens[ck(c)].item.numero, cnpjEmpresa: empresa.cnpj })), env);
  } finally { _nfechPortalRodando = false; }
  const fresco = _nfechCacheLer();               // outra consulta pode ter gravado enquanto a pessoa marcava o captcha
  const em = new Date().toISOString();
  let semCert = false;
  for (const c of lista) {
    const h = fresco.itens[ck(c)]; const r = res[c] || {};
    if (!h || !h.item) continue;
    if (r.ok) {
      h.item.eventos = r.eventos;
      h.item.portal = { em, n: r.eventos.length };
      if (r.autorizacao) { if (!h.item.dh_autorizacao) h.item.dh_autorizacao = r.autorizacao.quando; if (!h.item.protocolo) h.item.protocolo = r.autorizacao.protocolo; h.item.protAut = r.autorizacao; }
      if (/cancelad/.test(r.situacao) || r.eventos.some((x) => x.tipo === '110111')) h.item.situacao = 'cancelada';
    } else if (r.erro === 'cert') { h.item.portal = { em, erro: 'cert' }; semCert = true; }
    else if (r.erro === 'site') h.item.portal = { em, erro: 'site', motivo: r.motivo || '' };
  }
  _nfechCacheGravar(fresco);
  return { itens: lista.map((c) => ({ ...(fresco.itens[ck(c)] || {}).item, chave: c, consultadoEm: (fresco.itens[ck(c)] || {}).em || '' })), semCert, empresa: empresa.razaoSocial };
}));
ipcMain.handle('nfech:abrir', (_evt, { caminho, pasta }) => _mod('fiscal-nfechave')(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('Arquivo não encontrado (foi movido ou apagado?).');
  if (pasta) shell.showItemInFolder(caminho); else await shell.openPath(caminho);
  return {};
}));
ipcMain.handle('nfech:exportar', (_evt, { itens, titulo, nome }) => _mod('fiscal-nfechave')(async () => {
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar resultado da consulta',
    defaultPath: `${(nome || 'Consulta_NFe').replace(/[\\/:*?"<>|]/g, '_')}.xlsx`, filters: [{ name: 'Planilha Excel', extensions: ['xlsx'] }] });
  if (r.canceled || !r.filePath) return { cancelado: true };
  const entrada = path.join(os.tmpdir(), `fc_nfech_x_${Date.now()}.json`);
  const saida = entrada + '.res.json';
  fs.writeFileSync(entrada, JSON.stringify(itens || []));
  await runFiscal(['manifestacao-xlsx', r.filePath, '--entrada', entrada, '--titulo', String(titulo || ''), '--json', saida], saida);
  const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
  for (const f of [entrada, saida]) fs.unlink(f, () => {});
  if (res.erro) throw new Error(res.erro);
  shell.openPath(r.filePath);
  return { path: r.filePath };
}));

// ---------------------------------------------------------------------------
// Adaptação de planilhas — Admin e quem tiver o módulo "admin-planilhas" liberado. Lê uma ou várias planilhas de auditoria de itens e gera um NOVO Excel (Modelo 4)
// ao lado de cada original ("<nome> - OK.xlsx"). Os originais nunca são alterados.
// ---------------------------------------------------------------------------
function _planAnalisar(arquivos) {
  const tag = Date.now();
  const entrada = path.join(os.tmpdir(), `fc_plan_in_${tag}.json`);
  const saida = path.join(os.tmpdir(), `fc_plan_${tag}.json`);
  fs.writeFileSync(entrada, JSON.stringify(arquivos));
  return runFiscal(['planilha-auditoria', '-', '--acao', 'analisar-lote', '--entrada', entrada, '--json', saida], saida).then(() => {
    const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
    for (const f of [entrada, saida]) fs.unlink(f, () => {});
    if (res.erro) throw new Error(res.erro);
    return { itens: res.itens || [] };
  });
}
const _planGerada = (nome) => / - (OK|Profissional)( \(\d+\))?\.xls[xm]$/i.test(nome);
// várias planilhas de uma vez (Ctrl/Shift na janela)
ipcMain.handle('plan:escolher', () => _mod('admin-planilhas')(async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Planilhas para adaptar (pode escolher várias)', properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Planilha Excel', extensions: ['xlsx', 'xlsm'] }] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  return _planAnalisar(r.filePaths);
}));
// uma pasta inteira: pega as planilhas da pasta (sem subpastas), ignorando as já geradas e os temporários do Excel
ipcMain.handle('plan:pasta', () => _mod('admin-planilhas')(async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Pasta com as planilhas', properties: ['openDirectory'] });
  if (r.canceled || !r.filePaths.length) return { cancelado: true };
  const dir = r.filePaths[0];
  const arqs = fs.readdirSync(dir).filter((n) => /\.xls[xm]$/i.test(n) && !n.startsWith('~$') && !_planGerada(n)).map((n) => path.join(dir, n));
  if (!arqs.length) throw new Error('Nenhuma planilha (.xlsx) nesta pasta.');
  if (arqs.length > 200) throw new Error(`A pasta tem ${arqs.length} planilhas: escolha no máximo 200 por vez.`);
  return _planAnalisar(arqs);
}));
ipcMain.handle('plan:gerar', (_evt, { itens }) => _mod('admin-planilhas')(async () => {
  const lista = (itens || []).filter((x) => x && x.arquivo && fs.existsSync(x.arquivo)).map((x) => ({ arquivo: x.arquivo, titulo: String(x.titulo || '') }));
  if (!lista.length) throw new Error('Nenhuma planilha para gerar (foram movidas ou apagadas?).');
  const tag = Date.now();
  const entrada = path.join(os.tmpdir(), `fc_plan_g_in_${tag}.json`);
  const saida = path.join(os.tmpdir(), `fc_plan_g_${tag}.json`);
  const prog = path.join(os.tmpdir(), `fc_plan_g_prog_${tag}.json`);
  fs.writeFileSync(entrada, JSON.stringify(lista));
  const env = (d) => { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('plan:progresso', d); };
  env({ feitas: 0, total: lista.length, atual: path.basename(lista[0].arquivo) });
  const tm = setInterval(() => { try { env(JSON.parse(fs.readFileSync(prog, 'utf-8'))); } catch (_) {} }, 600);
  try {
    await runFiscal(['planilha-auditoria', '-', '--acao', 'gerar-lote', '--entrada', entrada, '--progresso', prog, '--json', saida], saida);
  } finally { clearInterval(tm); }
  const res = JSON.parse(fs.readFileSync(saida, 'utf-8'));
  for (const f of [entrada, saida, prog]) fs.unlink(f, () => {});
  if (res.erro) throw new Error(res.erro);
  return { itens: res.itens || [] };
}));
ipcMain.handle('plan:abrir', (_evt, { caminho, pasta }) => _mod('admin-planilhas')(async () => {
  if (!caminho || !fs.existsSync(caminho)) throw new Error('Arquivo não encontrado.');
  if (pasta) shell.showItemInFolder(caminho); else await shell.openPath(caminho);
  return {};
}));

ipcMain.handle('fiscal:nfseBaixar', async (_evt, { empresaId, dataInicial, dataFinal, gerarPdf }) => {
  const empresa = _lerIndiceCert().empresas.find((e) => e.id === empresaId);
  if (!empresa) return { error: 'Empresa não encontrada — cadastre o certificado primeiro.' };
  const r = await _baixarNfseEmpresa(empresa, dataInicial, dataFinal, gerarPdf);
  return r.error ? { error: r.error } : { ok: true, resultado: r.resultado };
});

// ---- Baixa em lote: todas as empresas cadastradas, uma por vez, período obrigatório ----
let _loteRodando = false;
let _loteCancelar = false;
const _doisDig = (n) => String(n).padStart(2, '0');
const _stampArquivo = (d) => `${d.getFullYear()}-${_doisDig(d.getMonth() + 1)}-${_doisDig(d.getDate())}_${_doisDig(d.getHours())}${_doisDig(d.getMinutes())}`;
const _dataHoraBR = (d) => `${_doisDig(d.getDate())}/${_doisDig(d.getMonth() + 1)}/${d.getFullYear()} ${_doisDig(d.getHours())}:${_doisDig(d.getMinutes())}`;

ipcMain.handle('fiscal:nfseLoteCancelar', () => {
  if (_loteRodando) _loteCancelar = true;      // termina a empresa em andamento e não começa as próximas
  return { ok: true };
});

ipcMain.handle('fiscal:nfseLoteIniciar', async (_evt, { dataInicial, dataFinal, gerarPdf }) => {
  if (_loteRodando) return { error: 'Já existe um lote em andamento.' };
  if (!dataInicial || !dataFinal) return { error: 'Informe o período (data inicial e data final) antes de baixar em lote.' };
  if (dataInicial > dataFinal) return { error: 'A data inicial não pode ser depois da data final.' };
  const empresas = (_lerIndiceCert().empresas || []).slice()
    .sort((a, b) => String(a.razaoSocial).localeCompare(String(b.razaoSocial), 'pt-BR'));
  if (!empresas.length) return { error: 'Nenhuma empresa cadastrada. Cadastre os certificados primeiro.' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde salvar os documentos antes de baixar em lote.' };

  _loteRodando = true;
  _loteCancelar = false;
  const inicio = new Date();
  const enviar = (p) => { try { if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('nfse:loteProgresso', p); } catch (_) {} };
  let resultados = [];
  try {
    resultados = await nfseLote.executarLote({
      empresas,
      baixarEmpresa: (emp) => _baixarNfseEmpresa(emp, dataInicial, dataFinal, gerarPdf),
      analisarEmpresa: (emp) => _analisarNfseEmpresa(emp, dataInicial, dataFinal, { vazioSePastaAusente: true }),
      salvarPainel: (emp, html) => {
        const cli = _cliDe({ nome: emp.razaoSocial, cnpj: emp.cnpj });
        const dCli = cli ? pastaCliente.pastaMes(cli.dir, dataInicial.slice(0, 4), dataInicial.slice(5, 7), true) : null;
        if (!dCli) return nfseLote.salvarPainelIndividual(pastaBase, emp, html, dataInicial, dataFinal);
        const sub = nfseLote.periodoSubpasta(dataInicial, dataFinal);
        const abs = path.join(dCli, `Painel NFS-e ${/^\d{4}-\d{2}$/.test(sub) ? sub.slice(5, 7) + sub.slice(0, 4) : sub}.html`);
        fs.writeFileSync(abs, html, 'utf-8');
        return { rel: abs, abs, dir: dCli };
      },
      onProgresso: enviar,
      cancelado: () => _loteCancelar,
    });
    const cancelado = _loteCancelar;
    const fim = new Date();
    const pasta = path.join(pastaBase, '_Relatorios em lote');
    fs.mkdirSync(pasta, { recursive: true });
    const caminho = path.join(pasta, `Lote_${dataInicial}_a_${dataFinal}_${_stampArquivo(fim)}.html`);
    const sub = nfseLote.periodoSubpasta(dataInicial, dataFinal);
    const dados = {
      periodo: { ini: dataInicial, fim: dataFinal }, inicio: _dataHoraBR(inicio), fim_exec: _dataHoraBR(fim), gerar_pdf: gerarPdf !== false, cancelado,
      caminho, pasta_relatorios: [pastaBase, `${String(dataInicial).slice(5, 7)}-${String(dataInicial).slice(0, 4)}`, '<Empresa>', 'NFS-e', 'Relatórios', sub].join(path.sep) + path.sep, empresas: resultados,
    };
    const inJson = path.join(os.tmpdir(), `fc_lote_${Date.now()}.json`);
    const outHtml = path.join(os.tmpdir(), `fc_lote_${Date.now()}.html`);
    fs.writeFileSync(inJson, JSON.stringify(dados), 'utf-8');
    try {
      await runFiscal(['nfse-lote-relatorio', '--entrada', inJson, '--saida', outHtml], outHtml);
    } catch (e) {
      return { error: `O lote terminou (${resultados.filter((r) => r.salvos).length} empresa(s) com notas), mas não consegui gerar o relatório geral: ${String(e.message || e)}` };
    }
    fs.writeFileSync(caminho, fs.readFileSync(outHtml, 'utf-8'), 'utf-8');
    [inJson, outHtml].forEach((x) => fs.unlink(x, () => {}));
    const cont = (k) => resultados.filter((r) => r.status === k).length;
    return {
      ok: true, caminho, pasta, url: require('url').pathToFileURL(caminho).href,
      resumo: {
        total: resultados.length, concluidas: cont('concluida'), sem_notas: cont('sem_notas'), puladas: cont('pulada'), erros: cont('erro'),
        nao_iniciadas: cont('nao_iniciada'), salvos: resultados.reduce((s, r) => s + (r.salvos || 0), 0),
        inconsistencias: resultados.reduce((s, r) => s + (r.inconsistencias || 0), 0), cancelado,
      },
    };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { _loteRodando = false; _loteCancelar = false; }
});

ipcMain.handle('fiscal:nfsePdfAbrir', async (_evt, { empresaId, chave }) => {
  const indice = _lerIndiceCert();
  const empresa = indice.empresas.find((e) => e.id === empresaId);
  if (!empresa) return { error: 'Empresa não encontrada.' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde os documentos são salvos primeiro.' };
  { const t = _nfseBase(empresa, pastaBase); if (t !== pastaBase && _temPastaEmpresa(t, empresa.razaoSocial)) pastaBase = t; }
  const pastaEmpresa = path.join(pastaBase, empresa.razaoSocial);
  const jsonTmp = path.join(os.tmpdir(), `fc_nfse_pdf_${Date.now()}.json`);
  try {
    await runFiscal(['nfse-pdf-chave', pastaEmpresa, chave, '--pasta-base', pastaBase, '--json', jsonTmp], jsonTmp);
    const res = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    fs.unlink(jsonTmp, () => {});
    if (res.erro) return { error: res.erro };
    shell.openPath(res.pdf);
    return { ok: true, pdf: res.pdf };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('changelog:check', async () => {
  try { return await changelog.checarNovidades(app.getVersion(), app.getPath('userData')); }
  catch (_) { return null; }
});
ipcMain.handle('changelog:marcarVisto', (_evt, versao) => {
  changelog.marcarComoVisto(app.getPath('userData'), versao);
  return { ok: true };
});
ipcMain.handle('license:listAll', async () => {
  if (sessionRole !== 'admin') return { error: 'Acesso restrito ao Admin.' };
  try { return { ok: true, itens: await cloud.listLicenses(app.getPath('userData')) }; }
  catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('license:setStatus', async (_evt, { codigo, status }) => {
  if (sessionRole !== 'admin') return { error: 'Acesso restrito ao Admin.' };
  try { return await cloud.setLicenseStatus(app.getPath('userData'), codigo, status); }
  catch (e) { return { error: String(e.message || e) }; }
});

// ---- Histórico de balancetes (nuvem) ----
ipcMain.handle('cloud:listEmpresas', async () => {
  try { return { ok: true, itens: await cloud.listEmpresas() }; }
  catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('cloud:listHistorico', async (_evt, cnpj) => {
  try { return { ok: true, itens: await cloud.listHistorico(cnpj) }; }
  catch (e) { return { error: String(e.message || e) }; }
});
// ---------------------------------------------------------------------------
// Chat de Ajuda Tributária — a chave da API nunca sai do processo principal
// (renderer só manda a mensagem e recebe o texto de volta). Busca na web
// SEMPRE ligada, porque tributário muda toda hora e "de cabeça" não serve.
// ---------------------------------------------------------------------------
// As instruções do chat e a chave da Anthropic ficam na função chatIA, no servidor do Google (functions/).
ipcMain.handle('ia:enviarMensagem', async (_evt, { mensagem, historico }) => {
  try {
    const r = await auth.chatIA(mensagem, historico || []);
    return { ok: true, texto: r.texto, resposta: r.resposta };
  } catch (e) {
    return { error: 'Falha ao falar com a IA: ' + String(e.message || e) };
  }
});

// ---------------------------------------------------------------------------
// Módulo Conciliação de Fornecedores — roda o extrato_core.py
// ---------------------------------------------------------------------------
function extratoScriptPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'python', 'extrato_core.py')
    : path.join(__dirname, '..', 'python', 'extrato_core.py');
}
function extratoRunner() {
  if (app.isPackaged) {
    const bin = process.platform === 'win32' ? 'extrato_core.exe' : 'extrato_core';
    return { cmd: path.join(process.resourcesPath, 'bin', bin), base: [] };
  }
  const { cmd } = pythonCore();
  return { cmd, base: [extratoScriptPath()] };
}
function runExtrato(cliArgs, readyFile) {
  return new Promise((resolve, reject) => {
    const runner = extratoRunner();
    let child;
    try {
      child = spawn(runner.cmd, [...runner.base, ...cliArgs], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
        windowsHide: true,
      });
    } catch (e) { return reject(e); }
    let err = '';
    if (child.stderr) child.stderr.on('data', (d) => (err += d.toString()));
    if (child.stdout) child.stdout.on('data', () => {});
    const t0 = Date.now();
    const timer = setInterval(() => {
      if (fs.existsSync(readyFile)) {
        try {
          const st = fs.statSync(readyFile);
          if (st.size > 0) { clearInterval(timer); try { child.kill(); } catch (_) {} resolve(); return; }
        } catch (_) {}
      }
      if (Date.now() - t0 > 120000) { clearInterval(timer); try { child.kill(); } catch (_) {} reject(new Error('Tempo esgotado. ' + err.slice(0, 300))); }
    }, 150);
    child.on('error', (e) => { clearInterval(timer); reject(e); });
    child.on('close', (code) => {
      setTimeout(() => {
        if (fs.existsSync(readyFile)) return;
        clearInterval(timer);
        reject(new Error('Falha no núcleo de conciliação (código ' + code + '). ' + err.slice(0, 400)));
      }, 400);
    });
  });
}

let planoContasCache = null; // { caminho, fornecedoresPath (json no disco) }

ipcMain.handle('conciliacao:pickPlanoContas', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar plano de contas (Word)',
    filters: [{ name: 'Word', extensions: ['docx'] }],
    properties: ['openFile'],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  const caminho = res.filePaths[0];
  const jsonOut = path.join(os.tmpdir(), `fc_planocontas_${Date.now()}.json`);
  try {
    await runExtrato(['--plano-contas', caminho, '--json', jsonOut], jsonOut);
    const dados = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    planoContasCache = { caminho, total: dados.total, fornecedores: dados.fornecedores };
    return { ok: true, total: dados.total, arquivo: path.basename(caminho) };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(jsonOut, () => {});
  }
});

ipcMain.handle('conciliacao:pickExtrato', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar extrato bancário (Word)',
    filters: [{ name: 'Word', extensions: ['docx'] }],
    properties: ['openFile'],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, path: res.filePaths[0] };
});

ipcMain.handle('conciliacao:conciliar', async (_evt, { banco, extratoPath, ano }) => {
  if (!planoContasCache) return { error: 'Importe o plano de contas antes.' };
  const fornecedoresPath = path.join(os.tmpdir(), `fc_fornecedores_${Date.now()}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_conciliado_${Date.now()}.json`);
  try {
    fs.writeFileSync(fornecedoresPath, JSON.stringify(planoContasCache.fornecedores));
    const args = ['--conciliar', '--banco', banco, '--extrato', extratoPath,
                   '--fornecedores', fornecedoresPath, '--json', jsonOut];
    if (ano) args.push('--ano', String(ano));
    await runExtrato(args, jsonOut);
    const dados = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    return { ok: true, ...dados };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(fornecedoresPath, () => {});
    fs.unlink(jsonOut, () => {});
  }
});

ipcMain.handle('conciliacao:pickTxtOriginal', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecionar o lançamento original (TXT do Domínio)',
    filters: [{ name: 'TXT', extensions: ['txt'] }],
    properties: ['openFile'],
  });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  return { canceled: false, path: res.filePaths[0] };
});

ipcMain.handle('conciliacao:exportarTxt', async (_evt, { txtOriginalPath, mapa, sugestao }) => {
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar TXT conciliado (pronto pra importar no Domínio)',
    defaultPath: (sugestao || 'lancamento-conciliado') + '.txt',
    filters: [{ name: 'TXT', extensions: ['txt'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  const mapaPath = path.join(os.tmpdir(), `fc_mapa_${Date.now()}.json`);
  try {
    fs.writeFileSync(mapaPath, JSON.stringify(mapa));
    await runExtrato(['--gerar-txt', '--original', txtOriginalPath, '--mapa', mapaPath, '--saida', save.filePath], save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(mapaPath, () => {});
  }
});

ipcMain.handle('cloud:getHistoricoItem', async (_evt, { cnpj, id }) => {
  try {
    const data = await cloud.getHistoricoItem(cnpj, id);
    // Sem isso, Indicadores/Exportar ficavam "sem fonte" pra um item vindo do
    // Histórico (não existe PDF local nesse caso) — grava o dado já parseado
    // num JSON temporário e aponta lastJsonPath pra ele, mesmo cache que um
    // import normal usa. lastPdfPath fica null de propósito (não existe PDF
    // aqui) — os handlers de exportar/Indicadores precisam aceitar isso.
    if (lastJsonPath) fs.unlink(lastJsonPath, () => {});
    const jsonTmp = path.join(os.tmpdir(), `fc_hist_${Date.now()}.json`);
    fs.writeFileSync(jsonTmp, JSON.stringify(data));
    lastJsonPath = jsonTmp;
    lastPdfPath = null;
    return { ok: true, data };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('cloud:deleteHistoricoItem', async (_evt, { cnpj, id }) => {
  try { return await cloud.deleteHistoricoItem(cnpj, id); }
  catch (e) { return { error: String(e.message || e) }; }
});

// ---- Atualização automática ----
ipcMain.handle('updater:installNow', (_e, versao) => { updater.installNow(true, String(versao || '')); });

ipcMain.handle('app:diag', async () => {
  const { cmd, baseArgs } = pythonCore();
  return {
    packaged: app.isPackaged,
    cmd,
    script: baseArgs[0] || null,
    coreExists: app.isPackaged ? fs.existsSync(cmd) : true,
    userData: app.getPath('userData'),
  };
});

// ---------------------------------------------------------------------------
// IPC: exportar PDF do cliente (HTML -> printToPDF via Chromium)
// ---------------------------------------------------------------------------
ipcMain.handle('balancete:exportPdf', async (_evt, sugestao) => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes de exportar.' };

  const htmlOut = path.join(os.tmpdir(), `fiscocont_${Date.now()}.html`);
  try {
    const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
    await runCore([src, '--html', htmlOut], htmlOut, 'exists');
  } catch (e) {
    return { error: 'Falha ao gerar o relatório: ' + String(e.message || e) };
  }

  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar PDF do cliente',
    defaultPath: (sugestao || 'analise-balancete') + '.pdf',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlOut, () => {}); return { canceled: true }; }

  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(htmlOut);
    await new Promise((r) => setTimeout(r, 350)); // deixa fontes/SVG assentarem
    const pdf = await worker.webContents.printToPDF({
      printBackground: true,
      pageSize: 'A4',
      margins: { marginType: 'default' },
    });
    fs.writeFileSync(save.filePath, pdf);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    worker.destroy();
    fs.unlink(htmlOut, () => {});
  }
});

ipcMain.handle('contabil:indicadoresHtml', async () => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes.' };
  const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
  const htmlOut = path.join(os.tmpdir(), `fc_ind_${Date.now()}.html`);
  try {
    await runCore([src, '--indicadores-html', htmlOut], htmlOut, 'exists');
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
    return { ok: true, html };
  } catch (e) {
    return { error: 'Falha ao gerar os indicadores: ' + String(e.message || e) };
  }
});

ipcMain.handle('contabil:exportIndicadores', async (_evt, sugestao) => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes de exportar.' };
  const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
  const htmlOut = path.join(os.tmpdir(), `fc_ind_${Date.now()}.html`);
  try {
    await runCore([src, '--indicadores-html', htmlOut], htmlOut, 'exists');
  } catch (e) {
    return { error: 'Falha ao gerar o relatório: ' + String(e.message || e) };
  }
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar PDF dos indicadores',
    defaultPath: (sugestao || 'indicadores') + '.pdf',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlOut, () => {}); return { canceled: true }; }
  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(htmlOut);
    await new Promise((r) => setTimeout(r, 1500));
    const pdf = await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', margins: { marginType: 'default' } });
    fs.writeFileSync(save.filePath, pdf);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    worker.destroy();
    fs.unlink(htmlOut, () => {});
  }
});

ipcMain.handle('balancete:exportInvertidas', async (_evt, sugestao) => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes de exportar.' };

  const htmlOut = path.join(os.tmpdir(), `fiscocont_inv_${Date.now()}.html`);
  try {
    const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
    await runCore([src, '--invertidas-html', htmlOut], htmlOut, 'exists');
  } catch (e) {
    return { error: 'Falha ao gerar o relatório: ' + String(e.message || e) };
  }

  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar PDF dos saldos invertidos',
    defaultPath: (sugestao || 'saldos-invertidos') + '.pdf',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlOut, () => {}); return { canceled: true }; }

  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(htmlOut);
    await new Promise((r) => setTimeout(r, 350));
    const pdf = await worker.webContents.printToPDF({
      printBackground: true,
      pageSize: 'A4',
      margins: { marginType: 'default' },
    });
    fs.writeFileSync(save.filePath, pdf);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    worker.destroy();
    fs.unlink(htmlOut, () => {});
  }
});

ipcMain.handle('balancete:exportBalanceteCompleto', async (_evt, sugestao) => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes de exportar.' };

  const htmlOut = path.join(os.tmpdir(), `fiscocont_balcompl_${Date.now()}.html`);
  try {
    const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
    await runCore([src, '--balancete-completo-html', htmlOut], htmlOut, 'exists');
  } catch (e) {
    return { error: 'Falha ao gerar o relatório: ' + String(e.message || e) };
  }

  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar PDF do balancete completo',
    defaultPath: (sugestao || 'balancete-completo') + '.pdf',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlOut, () => {}); return { canceled: true }; }

  // Paisagem de propósito — a tabela tem 6 colunas e fica larga demais pra retrato.
  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  try {
    await worker.loadFile(htmlOut);
    await new Promise((r) => setTimeout(r, 350));
    const pdf = await worker.webContents.printToPDF({
      printBackground: true,
      pageSize: 'A4',
      landscape: true,
      margins: { marginType: 'default' },
    });
    fs.writeFileSync(save.filePath, pdf);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    worker.destroy();
    fs.unlink(htmlOut, () => {});
  }
});

ipcMain.handle('balancete:exportDreCompleta', async (_evt, { fmt, sugestao, cliente }) => {
  if (!lastPdfPath && !lastJsonPath) return { error: 'Importe um balancete antes de exportar.' };

  const htmlTmp = path.join(os.tmpdir(), `fiscocont_dre2_${Date.now()}.html`);
  try {
    const src = (lastJsonPath && fs.existsSync(lastJsonPath)) ? lastJsonPath : lastPdfPath;
    const args = [src, '--dre-completa-html', htmlTmp];
    if (cliente) args.push('--cliente');
    await runCore(args, htmlTmp, 'exists');
  } catch (e) {
    return { error: 'Falha ao gerar o relatório: ' + String(e.message || e) };
  }

  const nomeBase = (sugestao || 'dre-completa') + (cliente ? '-cliente' : '');
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar ' + fmt.toUpperCase() + ' da DRE completa' + (cliente ? ' (para o cliente)' : ''),
    defaultPath: nomeBase + (fmt === 'pdf' ? '.pdf' : '.html'),
    filters: [{ name: fmt.toUpperCase(), extensions: [fmt] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlTmp, () => {}); return { canceled: true }; }

  try {
    if (fmt === 'html') {
      fs.copyFileSync(htmlTmp, save.filePath);
    } else {
      const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
      try {
        await worker.loadFile(htmlTmp);
        await new Promise((r) => setTimeout(r, 1600)); // deixa a animação do donut concluir
        const pdf = await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', margins: { marginType: 'default' } });
        fs.writeFileSync(save.filePath, pdf);
      } finally { worker.destroy(); }
    }
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(htmlTmp, () => {});
  }
});

// ---------------------------------------------------------------------------
// Módulo Fiscal — roda o fiscal_core.py e gera dashboards/conferência
// ---------------------------------------------------------------------------
function fiscalScriptPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'python', 'fiscal_core.py')
    : path.join(__dirname, '..', 'python', 'fiscal_core.py');
}

// Resolve como rodar o núcleo fiscal:
//  - empacotado: fiscal_core.exe (compilado)
//  - dev/portátil: Python (do .venv) + fiscal_core.py
// ✦ Análise ampla pelo POP (Corretor do SPED Fiscal · só Admin · EM TESTE). Só roda quando o Admin clica em
// "Analisar com IA": confere o SPED item a item do POP (Python), busca na nuvem os DAREs pagos e o Fisconforme da
// inscrição, manda os achados (sem CNPJ e sem nomes) para a função analisePop e junta a resposta.
function _cab0000Arq(arq) {
  try {
    const fd = fs.openSync(arq, 'r'); const b = Buffer.alloc(800); fs.readSync(fd, b, 0, 800, 0); fs.closeSync(fd);
    const l = b.toString('latin1').replace(/^﻿/, '').split(/\r?\n/)[0].split('|');
    if (l[1] !== '0000') return null;
    return { dtIni: l[4], dtFin: l[5], ie: String(l[10] || '').replace(/\D/g, '').replace(/^0+/, ''), uf: l[9] };
  } catch (_) { return null; }
}
async function _popExtras(cab) {
  const out = { pagos: [], fisconforme: [], consultou_pagos: false, consultou_fisconforme: false };
  const db = auth.db(); if (!db || !cab || !cab.ie) return out;
  const f = auth.fsMod();
  const mes = `${cab.dtIni.slice(4, 8)}${cab.dtIni.slice(2, 4)}`;
  try {
    (await f.getDocs(f.collection(db, 'dare'))).forEach((d) => {
      if (!d.id.startsWith(`pg_${mes}_`)) return;
      const x = d.data();
      if (String(x.ie || '').replace(/\D/g, '').replace(/^0+/, '') !== cab.ie) return;
      out.consultou_pagos = !x.erro;
      out.pagos = (x.pagos || []).map((p) => ({ nr: p.nr, parc: p.parc, rec: p.rec, venc: p.venc, pagoEm: p.pagoEm, valorN: p.valorN, pagoN: p.pagoN }));
    });
  } catch (_) {}
  try {
    let lida = false;
    (await f.getDocs(f.collection(db, 'fisconforme'))).forEach((d) => {
      if (d.id === '_meta') { lida = true; return; }
      if (d.id.startsWith('_')) return;
      const x = d.data();
      if (String(x.ie || '').replace(/\D/g, '').replace(/^0+/, '') !== cab.ie) return;
      out.fisconforme.push({ codigo: x.codigo, periodo: x.periodo, desc: x.desc, status: x.status });
    });
    out.consultou_fisconforme = lida;
  } catch (_) {}
  return out;
}
ipcMain.handle('pop:estado', async () => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  try {
    const db = auth.db(); const f = auth.fsMod();
    const d = (await f.getDoc(f.doc(db, 'segredos_admin', 'pop_icms'))).data();
    return { ok: true, pop: d ? { nome: d.nome || '', em: d.em || '', paginas: d.paginas || 0, tamanho: (d.texto || '').length } : null };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('pop:carregar', async () => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'POP do Fiscal — EFD ICMS/IPI (PDF)', properties: ['openFile'], filters: [{ name: 'PDF', extensions: ['pdf'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  const jsonOut = path.join(os.tmpdir(), `fc_pop_${Date.now()}.json`);
  try {
    await runFiscal(['pop-texto', '--pdf', r.filePaths[0], '--json', jsonOut], jsonOut);
    const t = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (!t.texto || t.texto.trim().length < 200) return { error: 'Não consegui ler o texto do PDF (ele precisa ter texto, não só imagem).' };
    const db = auth.db(); const f = auth.fsMod();
    const d = { texto: t.texto.slice(0, 150000), nome: path.basename(r.filePaths[0]), paginas: t.paginas || 0, em: new Date().toISOString(), por: (auth.sessao() || {}).email || '' };
    await f.setDoc(f.doc(db, 'segredos_admin', 'pop_icms'), d);
    return { ok: true, pop: { nome: d.nome, em: d.em, paginas: d.paginas, tamanho: d.texto.length } };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('pop:analisar', async (_evt, { spedPath, usarCorrigido, xmls, spedAnt }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const st = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_pop_res_${st}.json`), extraJ = path.join(os.tmpdir(), `fc_pop_extra_${st}.json`);
  const iaJ = path.join(os.tmpdir(), `fc_pop_ia_${st}.json`), finalJ = path.join(os.tmpdir(), `fc_pop_fim_${st}.json`);
  const prog = (t) => { try { mainWindow.webContents.send('pop:progresso', t); } catch (_) {} };
  let regimes = null;
  try {
    prog('Buscando os DAREs pagos e o Fisconforme da inscrição…');
    const cab = _cab0000Arq(base.arq);
    fs.writeFileSync(extraJ, JSON.stringify(await _popExtras(cab)), 'utf-8');
    prog('Conferindo o SPED item a item do POP…');
    regimes = await _regimesJson([base.arq]);
    await runFiscal(['analise-pop', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), ...(spedAnt ? ['--sped-ant', spedAnt] : []),
      '--regimes', regimes, '--extra', extraJ, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    if (res.erro) return { error: res.erro };
    prog('Analisando os achados com a IA…');
    let ia = null, avisoIa = '';
    try { ia = (await auth.analisePop(res.para_ia)).ia; } catch (e) { avisoIa = String(e.message || e); }
    delete res.para_ia;
    fs.writeFileSync(jsonOut, JSON.stringify(res), 'utf-8');
    fs.writeFileSync(iaJ, JSON.stringify(ia || {}), 'utf-8');
    await runFiscal(['analise-pop', '--res', jsonOut, '--ia', iaJ, '--json', finalJ], finalJ);
    const fim = JSON.parse(fs.readFileSync(finalJ, 'utf-8'));
    if (fim.erro) return { error: fim.erro };
    return { ok: true, res: fim, avisoIa, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { for (const x of [jsonOut, extraJ, iaJ, finalJ, regimes]) if (x) fs.unlink(x, () => {}); }
});
ipcMain.handle('pop:pickSpedAnt', async () => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'SPED Fiscal do mês anterior (transporte de crédito)', properties: ['openFile'], filters: [{ name: 'SPED', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  const cab = _cab0000Arq(r.filePaths[0]);
  if (!cab) return { error: 'Esse arquivo não é um SPED Fiscal.' };
  return { ok: true, path: r.filePaths[0], periodo: `${cab.dtIni.slice(2, 4)}/${cab.dtIni.slice(4, 8)}` };
});
ipcMain.handle('pop:word', async (_evt, res) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  const nome = `Observações ${String(res?.cab?.nome || 'cliente').replace(/[\\/:*?"<>|]+/g, ' ').trim()} ${String(res?.periodo || '').replace('/', '-')}.docx`;
  const save = await dialog.showSaveDialog(mainWindow, { title: 'Salvar o Word de observação', defaultPath: nome, filters: [{ name: 'Word', extensions: ['docx'] }] });
  if (save.canceled || !save.filePath) return { canceled: true };
  const st = Date.now(), resJ = path.join(os.tmpdir(), `fc_pop_w_${st}.json`), outJ = path.join(os.tmpdir(), `fc_pop_wo_${st}.json`);
  try {
    fs.writeFileSync(resJ, JSON.stringify(res), 'utf-8');
    await runFiscal(['analise-pop', '--res', resJ, '--word', save.filePath, '--json', outJ], outJ);
    const r = JSON.parse(fs.readFileSync(outJ, 'utf-8'));
    if (r.erro) return { error: r.erro };
    shell.openPath(save.filePath);
    return { ok: true, arquivo: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { for (const x of [resJ, outJ]) fs.unlink(x, () => {}); }
});

function fiscalRunner() {
  if (app.isPackaged) {
    const bin = process.platform === 'win32' ? 'fiscal_core.exe' : 'fiscal_core';
    return { cmd: path.join(process.resourcesPath, 'bin', bin), base: [] };
  }
  const { cmd } = pythonCore(); // interpretador Python do venv em dev
  return { cmd, base: [fiscalScriptPath()] };
}

function runFiscal(cliArgs, readyFile, prog) {   // prog: { arq, cb } — etapa real lida do núcleo enquanto roda (2.4.34)
  return new Promise((resolve, reject) => {
    const runner = fiscalRunner();
    let child;
    try {
      child = spawn(runner.cmd, [...runner.base, ...cliArgs], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', FISCOCONT_LOGO: logoPath() },
        windowsHide: true,
      });
    } catch (e) { return reject(e); }

    let err = '';
    if (child.stderr) child.stderr.on('data', (d) => (err += d.toString()));
    if (child.stdout) child.stdout.on('data', () => {});
    const t0 = Date.now();
    let progUlt = '';
    const timer = setInterval(() => {
      if (prog && prog.arq) {
        try { const t = fs.readFileSync(prog.arq, 'utf-8'); if (t && t !== progUlt) { progUlt = t; prog.cb(JSON.parse(t)); } } catch (_) {}
      }
      if (fs.existsSync(readyFile)) {
        try {
          const st = fs.statSync(readyFile);
          if (st.size > 0) { clearInterval(timer); try { child.kill(); } catch (_) {} resolve(); return; }
        } catch (_) {}
      }
      // 8 min — com volumes grandes de XML (milhares de arquivos), o antivírus do
      // Windows escaneando cada abertura de arquivo pode somar bastante tempo,
      // mesmo o processamento em si sendo rápido (medido: 11 mil XMLs processam
      // em ~1s puro, mas o total real pode passar de 1 min com esse overhead).
      if (Date.now() - t0 > 480000) { clearInterval(timer); try { child.kill(); } catch (_) {} reject(new Error('Tempo esgotado ao processar. ' + err.slice(0, 300))); }
    }, 150);
    child.on('error', (e) => { clearInterval(timer); reject(e); });
    child.on('close', (code) => {
      setTimeout(() => {
        if (fs.existsSync(readyFile)) return;
        clearInterval(timer);
        reject(new Error('Falha no núcleo fiscal (código ' + code + '). ' + err.slice(0, 400)));
      }, 400);
    });
  });
}

ipcMain.handle('fiscal:pickSped', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione o arquivo do SPED Fiscal (.txt)',
    filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }],
    properties: ['openFile'],
  });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return { path: r.filePaths[0] };
});

// ---------------------------------------------------------------------------
// Módulos exclusivos do Admin: Radar de Oportunidades e Levantamento para a Legalização.
// Tudo aqui exige papel "admin" também no processo principal (não só no menu).
// ---------------------------------------------------------------------------
function _soAdmin() {
  const liberado = sessionRole === 'admin'
    || (Array.isArray(sessionModulos) && sessionModulos.some((m) => m.startsWith('admin-') && !ADMIN_EXCLUSIVOS.has(m)));
  if (!liberado) return { error: 'Acesso restrito ao Admin.' };
  if (sessionLocked) return { error: 'Sessão travada por inatividade: digite a senha para continuar.' };
  return null;
}
// Ferramentas avulsas do Corretor do SPED (DIFAL, Simples, ICMS × XML, lote…): só o Admin, mesmo com o Corretor
// liberado para a pessoa — a equipe usa só a Análise Inteligente (admin:tudoAnalisar / admin:tudoAplicar).
function _soAdminCorretor() {
  if (sessionRole !== 'admin') return { error: 'Esta ferramenta do Corretor é só do Admin. Use a Análise Inteligente.' };
  if (sessionLocked) return { error: 'Sessão travada por inatividade: digite a senha para continuar.' };
  return null;
}

// ✨ Análise Inteligente: o que a equipe recebe. O Admin liga/desliga cada conferência (Firestore config_equipe/corretor,
// vale na hora para todo mundo). Conferência nova entra com teste: true — fica desligada para a equipe até o Admin ligar.
// A Validação do PVA é a base das outras e sempre roda. O Estoque que saiu da ST fica fora (só o Admin, botão próprio).
const CORR_ETAPAS = [
  { key: 'validacao', nome: 'Validação do PVA', fixo: true },
  { key: 'pvacad', nome: 'Validação do PVA · cadastro e ajustes', teste: true },
  { key: 'chave', nome: 'Chave de acesso × XML', teste: true },
  { key: 'ncm', nome: 'NCM × XML das entradas', teste: true },
  { key: 'ucons', nome: 'Uso e consumo lançado como revenda', teste: true },
  { key: 'comb', nome: 'Combustível × uso e consumo' },
  { key: 'stent', nome: 'ICMS-ST na entrada', teste: true },
  { key: 'difal', nome: 'Uso e consumo · DIFAL e crédito' },
  { key: 'desconto', nome: 'Desconto × XML' },
  { key: 'icms', nome: 'ICMS creditado × XML' },
  { key: 'valor', nome: 'Valor e base × XML' },
  { key: 'simples', nome: 'Crédito do Simples' },
  { key: 'maca', nome: 'Crédito maçã e pera' },
  { key: 'alcgm', nome: 'Crédito presumido ALC Guajará-Mirim' },
  { key: 'abatnt', nome: 'Abatimento nos itens (C170 campo 38)' },
  { key: 'acum', nome: 'Acumulador 7000' },
  { key: 'cad', nome: 'Cadastro de produtos (0200)' },
  { key: 'unid', nome: 'Unidade × XML' },
];
const CORR_DOC = ['config_equipe', 'corretor'];
async function _corrEquipeCfg() {
  const db = auth.db(); const f = auth.fsMod();
  if (!db) throw new Error('Entre com o seu usuário para usar a Análise Inteligente.');
  const snap = await f.getDoc(f.doc(db, ...CORR_DOC));
  return snap.exists() ? (snap.data().etapas || {}) : {};
}
const _corrLigada = (cfg, e) => e.fixo || (cfg[e.key] !== undefined ? !!cfg[e.key] : !e.teste);
// lista de --etapas para quem não é Admin (Admin: sem limite)
async function _corrPermitidas() {
  if (sessionRole === 'admin') return null;
  const cfg = await _corrEquipeCfg();
  return CORR_ETAPAS.filter((e) => _corrLigada(cfg, e)).map((e) => e.key);
}
function _soCorretor() {
  if (!_podeModulo('admin-corrigir-sped')) return { error: 'O Corretor do SPED não está liberado para você. Peça ao Admin para liberar em Usuários › Módulos.' };
  if (sessionLocked) return { error: 'Sessão travada por inatividade: digite a senha para continuar.' };
  return null;
}
ipcMain.handle('corr:equipeLer', () => _adm(async () => {
  const cfg = await _corrEquipeCfg();
  return { etapas: CORR_ETAPAS.map((e) => ({ ...e, ligada: _corrLigada(cfg, e) })) };
}));
ipcMain.handle('corr:equipeSalvar', (_evt, { key, ligada }) => _adm(async () => {
  const e = CORR_ETAPAS.find((x) => x.key === key);
  if (!e) throw new Error('Conferência desconhecida.');
  if (e.fixo) throw new Error('A Validação do PVA sempre roda: é a base das outras conferências.');
  const db = auth.db(); const f = auth.fsMod();
  const s = auth.sessao() || {};
  await f.setDoc(f.doc(db, ...CORR_DOC), { etapas: { [key]: !!ligada }, atualizadoEm: f.serverTimestamp(), atualizadoPor: s.nome || s.email || '' }, { merge: true });
  return { key, ligada: !!ligada };
}));

function _jsonUser(nome, padrao) {
  try { return JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), nome), 'utf-8')); } catch (_) { return padrao; }
}
function _salvarJsonUser(nome, dados) {
  fs.writeFileSync(path.join(app.getPath('userData'), nome), JSON.stringify(dados, null, 1), 'utf-8');
}

ipcMain.handle('admin:radarPick', async (_evt, { tipo }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  let opts;
  if (tipo === 'xml') {
    opts = { title: 'Selecione os XMLs das notas (arquivos .xml ou .zip)', properties: ['openFile', 'multiSelections'],
             filters: [{ name: 'XML ou ZIP', extensions: ['xml', 'zip'] }] };
  } else if (tipo === 'xmlpasta') {
    opts = { title: 'Selecione a pasta com os XMLs das notas', properties: ['openDirectory', 'multiSelections'] };
  } else {
    const fiscal = tipo === 'fiscal';
    opts = { title: fiscal ? 'Selecione as EFD ICMS/IPI do cliente (opcional, para o CIAP)' : 'Selecione as EFD-Contribuições do cliente (um ou mais meses)',
             properties: ['openFile', 'multiSelections'], filters: [{ name: fiscal ? 'EFD ICMS/IPI' : 'EFD-Contribuições', extensions: ['txt'] }] };
  }
  const r = await dialog.showOpenDialog(mainWindow, opts);
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});

ipcMain.handle('admin:radarAnalisar', async (_evt, { efdc, fiscal, xml }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!efdc || !efdc.length) return { error: 'Selecione ao menos uma EFD-Contribuições.' };
  const jsonOut = path.join(os.tmpdir(), `fc_radar_${Date.now()}.json`);
  try {
    const args = ['radar-oportunidades', '--efdc', ...efdc];
    if (fiscal && fiscal.length) args.push('--fiscal', ...fiscal);
    if (xml && xml.length) args.push('--xml', ...xml);
    args.push('--json', jsonOut);
    await runFiscal(args, jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    const status = _jsonUser('radar-status.json', {});
    return { ok: true, res, status };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- BI da Empresa (Admin · teste)
// Cada análise concluída guarda um RESUMO (totais e contagens; nunca XML ou arquivo do cliente) neste computador:
// userData/bi-historico.json. Uma entrada por empresa (CNPJ) + competência + módulo; a análise mais nova substitui.
function _biPath() { return path.join(app.getPath('userData'), 'bi-historico.json'); }
function _biLer() { try { const j = JSON.parse(fs.readFileSync(_biPath(), 'utf-8')); return Array.isArray(j) ? j : []; } catch (_) { return []; } }
function _biComp(v) {
  const t = String(v || '');
  let m = t.match(/^(\d{4})-(\d{2})/); if (m) return `${m[1]}-${m[2]}`;
  m = t.match(/^(\d{2})(\d{2})(\d{4})$/); if (m) return `${m[3]}-${m[2]}`;
  m = t.match(/(\d{2})\/(\d{2})\/(\d{4})/); if (m) return `${m[3]}-${m[2]}`;
  return '';
}
function _biRegistrar(modulo, r, extra = {}) {
  try {
    if (!r || r.erro) return;
    const dig = (x) => String(x || '').replace(/\D/g, '');
    let reg = null;
    const n = (x) => Number(x) || 0;
    if (modulo === 'analise') {
      const st = r.situacao || {}, temas = [];
      Object.entries(r.temas || {}).forEach(([t, q]) => { const k = n(q.Divergente) + n(q.Verificar); if (k) temas.push({ tema: t, itens: k, div: n(q.Divergente) }); });
      reg = { cnpj: dig(r.cnpj), empresa: r.empresa, comp: _biComp((r.periodo || [])[0]),
        kpis: { entradas: n((r.totais || {}).vl), icms_cred: n((r.totais || {}).icms), icms_st: n((r.totais || {}).st), notas: n(r.notas), produtos: n(r.produtos) },
        pontos: { divergente: n((st.Divergente || [])[0]), verificar: n((st.Verificar || [])[0]) }, temas,
        por_tipo: (r.por_tipo || []).map(([nome, g]) => ({ nome, valor: n(g.vl) })) };
    } else if (modulo === 'apuracao') {
      const p = r.painel || {}, st = r.situacao || {};
      reg = { cnpj: dig(r.cnpj), empresa: r.empresa, comp: (r.meses || [])[0] || '',
        kpis: { ibscbs_debito: n((p.debito || {}).total), ibscbs_credito: n((p.credito || {}).total), ibscbs_saldo: n((p.saldo || {}).total) },
        pontos: { divergente: n(st.Divergente), verificar: n(st.Verificar) }, temas: (r.temas_bi || []).map((t) => ({ tema: t.tema, itens: t.itens, div: t.sit === 'Divergente' ? t.itens : 0 })) };
    } else if (modulo === 'frete') {
      reg = { cnpj: dig(r.cnpj), empresa: r.empresa, comp: r.competencia || '',
        kpis: { frete_credito: n((r.totais || {}).credito), frete_total: n((r.totais || {}).frete), frete_adicional: n(r.adicional_credito) },
        pontos: { divergente: 0, verificar: (r.pendencias || []).length }, temas: (r.pendencias || []).length ? [{ tema: 'Frete FOB · pendências', itens: r.pendencias.length, div: 0 }] : [] };
    } else if (modulo === 'deson') {
      const e = r.empresa || {};
      reg = { cnpj: dig(e.cnpj), empresa: e.empresa, comp: _biComp(e.periodo),
        kpis: { deson_total: n(r.total_deson), deson_notas: n(r.qtd_com_deson) }, pontos: { divergente: 0, verificar: 0 }, temas: [] };
    } else if (modulo === 'nfse') {
      const ret = (r.notas_com_retencao || []).reduce((a, x) => a + n(x.total_retido), 0);
      const inc = (r.inconsistencias_piscofins || []).length;
      reg = { cnpj: dig(extra.cnpj), empresa: extra.empresa, comp: extra.comp,
        kpis: { nfse_retido: Math.round(ret * 100) / 100, nfse_com_ret: n(r.qtd_com_retencao), nfse_notas: n(r.total_notas), nfse_prestado: n(r.valor_emitidas), nfse_tomado: n(r.valor_recebidas) },
        pontos: { divergente: 0, verificar: inc }, temas: inc ? [{ tema: 'NFS-e · retenção inconsistente', itens: inc, div: 0 }] : [] };
    }
    if (!reg || !reg.cnpj || !reg.comp) return;
    reg.modulo = modulo; reg.quando = new Date().toISOString();
    const hist = _biLer().filter((h) => !(h.cnpj === reg.cnpj && h.comp === reg.comp && h.modulo === modulo));
    hist.push(reg);
    fs.writeFileSync(_biPath(), JSON.stringify(hist.slice(-5000)), 'utf-8');
  } catch (_) { /* o BI nunca pode atrapalhar a análise */ }
}
ipcMain.handle('admin:biDados', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  return { ok: true, hist: _biLer() };
});
ipcMain.handle('admin:biExportar', async (_evt, { cnpj, nome }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const hist = _biLer().filter((h) => h.cnpj === cnpj);
  if (!hist.length) return { error: 'Nenhuma análise registrada para essa empresa.' };
  const base = `BI-${String(nome || cnpj).replace(/[^\w-]+/g, '_')}`.replace(/_+$/, '');
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar BI (Excel)', defaultPath: `${base}.xlsx`, filters: [{ name: 'Planilha Excel', extensions: ['xlsx'] }] });
  if (r.canceled || !r.filePath) return { canceled: true };
  const stamp = Date.now();
  const inJson = path.join(os.tmpdir(), `fc_bi_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_bi_res_${stamp}.json`);
  try {
    fs.writeFileSync(inJson, JSON.stringify(hist), 'utf-8');
    await runFiscal(['bi-excel', '--entrada', inJson, '--saida', r.filePath, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {}); fs.unlink(inJson, () => {});
    if (res.erro) return { error: res.erro };
    shell.openPath(r.filePath);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- Crédito de PIS/COFINS sobre frete FOB (Admin · teste)
let _fpUltimo = null;   // { args, html, nome }
ipcMain.handle('admin:fpPickXmls', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione os .zip com os CT-e e as NF-e de compra',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'ZIP', extensions: ['zip'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});
ipcMain.handle('admin:fpPickEfd', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'EFD-Contribuições do período (opcional)',
    properties: ['openFile'], filters: [{ name: 'EFD-Contribuições', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
ipcMain.handle('admin:fpPickSped', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'SPED Fiscal do período (opcional — pode escolher mais de um mês)',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});
ipcMain.handle('admin:fpAnalisar', async (_evt, { xmls, efd, sped, cnpj, excluirIcms }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!Array.isArray(xmls) || !xmls.length) return { error: 'Selecione os .zip com os CT-e e as NF-e.' };
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_fp_${stamp}.json`);
  const htmlOut = path.join(os.tmpdir(), `fc_fp_${stamp}.html`);
  const htmlCli = path.join(os.tmpdir(), `fc_fp_${stamp}_cliente.html`);   // versão do cliente (sem os CT-e em "Verificar")
  const args = ['frete-pis', '--xmls', ...xmls];
  if (efd) args.push('--efd', efd);
  if (Array.isArray(sped) && sped.length) args.push('--sped', ...sped);   // CFOP de entrada: uso e consumo / imobilizado
  const c = String(cnpj || '').replace(/\D/g, '');
  if (c) args.push('--cnpj', c);
  if (excluirIcms === false) args.push('--manter-icms');
  try {
    await runFiscal([...args, '--json', jsonOut, '--html', htmlOut, '--html-cliente', htmlCli], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    const html = fs.readFileSync(htmlOut, 'utf-8');
    if (_fpUltimo && _fpUltimo.html && _fpUltimo.html !== htmlOut) { fs.unlink(_fpUltimo.html, () => {}); if (_fpUltimo.cli) fs.unlink(_fpUltimo.cli, () => {}); }
    _fpUltimo = { args, html: htmlOut, cli: htmlCli, nome: res.empresa || res.cnpj || '' };
    _biRegistrar('frete', res);
    return { ok: true, res, html };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:fpExportar', async (_evt, { formato }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!_fpUltimo) return { error: 'Calcule o crédito primeiro.' };
  // HTML e PDF são para o cliente: saem da versão sem os CT-e em "Verificar". O Excel continua completo (conferência interna).
  const ext = formato === 'xlsx' ? 'xlsx' : formato === 'pdf' ? 'pdf' : 'html';
  const rot = { xlsx: ['Salvar Excel', 'Planilha Excel'], pdf: ['Salvar PDF', 'PDF'], html: ['Salvar HTML', 'Página HTML'] }[ext];
  const base = `Credito-PIS-COFINS-Frete-${String(_fpUltimo.nome || '').replace(/[^\w-]+/g, '_')}`.replace(/_+$/, '');
  const r = await dialog.showSaveDialog(mainWindow, { title: rot[0], defaultPath: `${base}.${ext}`, filters: [{ name: rot[1], extensions: [ext] }] });
  if (r.canceled || !r.filePath) return { canceled: true };
  const cli = _fpUltimo.cli && fs.existsSync(_fpUltimo.cli) ? _fpUltimo.cli : _fpUltimo.html;
  try {
    if (ext === 'html') fs.copyFileSync(cli, r.filePath);
    else if (ext === 'pdf') {
      const w = new BrowserWindow({ show: false, width: 1400, height: 1000, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
      try {
        await w.loadFile(cli);
        await new Promise((ok) => setTimeout(ok, 1200));
        fs.writeFileSync(r.filePath, await w.webContents.printToPDF({ landscape: true, printBackground: true, pageSize: 'A4',
          margins: { marginType: 'custom', top: 0.3, bottom: 0.3, left: 0.3, right: 0.3 } }));
      } finally { try { w.destroy(); } catch (_) {} }
    } else {
      const jsonOut = path.join(os.tmpdir(), `fc_fpx_${Date.now()}.json`);
      await runFiscal([..._fpUltimo.args, '--json', jsonOut, '--xlsx', r.filePath], jsonOut);
      const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
      if (res.erro) return { error: res.erro };
    }
    shell.openPath(r.filePath);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- Apuração Assistida IBS/CBS (Reforma Tributária) — equipe
// Lê os XMLs (.zip) de NF-e/NFC-e, apura débitos e créditos de IBS/CBS e confere CST/cClassTrib com a tabela oficial.
let _rtcUltimo = null;   // { args, html, nome }
ipcMain.handle('fiscal:rtcPickXmls', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione os .zip com os XMLs de NF-e e NFC-e (saídas e entradas)',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'ZIP', extensions: ['zip'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});
ipcMain.handle('fiscal:rtcPickSped', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'SPED Fiscal do mesmo período (opcional, só para conferência)',
    properties: ['openFile'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
// Atividade com regime específico do IBS/CBS que aparece em NF-e/NFC-e (tabela oficial cClassTrib):
//   • 200047 — Bares e restaurantes (LC 214/2025, arts. 273 a 276; redução de 40%, art. 275): CNAE principal 5611-2 ou 5612-1
//   • cooperativa (natureza jurídica 214-3): o regime do art. 271 (cClassTrib 200020/200054) vale só nas operações com
//     associados, não na empresa inteira — o sistema só avisa.
// Hotelaria, parques, agências de turismo, transporte, profissões intelectuais, saúde, educação e imóveis são serviços
// faturados por NFS-e e não entram nesta apuração (que lê NF-e e NFC-e).
function _atividadeRtc(api) {
  if (!api) return null;
  const cod = (c) => String(c || '').replace(/\D/g, '').padStart(7, '0');
  const fmt = (c) => `${c.slice(0, 4)}-${c.slice(4, 5)}/${c.slice(5)}`;
  const pri = cod(api.cnae_fiscal || (api.atividade_principal && api.atividade_principal[0] && api.atividade_principal[0].code));
  const priDesc = api.cnae_fiscal_descricao || (api.atividade_principal && api.atividade_principal[0] && api.atividade_principal[0].text) || '';
  const sec = (api.cnaes_secundarios || api.atividades_secundarias || []).map((x) => cod(x.codigo || x.code)).filter((c) => c !== '0000000');
  const nat = String(api.codigo_natureza_juridica || api.natureza_juridica || '').replace(/\D/g, '');
  const bar = (c) => /^(5611|5612)/.test(c);
  if (bar(pri)) return { regime: '200047', origem: `CNAE principal ${fmt(pri)}${priDesc ? ' – ' + priDesc : ''}` };
  const avisos = [];
  if (sec.some(bar)) avisos.push(`a empresa tem bar/restaurante como atividade secundária (CNAE ${fmt(sec.find(bar))}); se for a atividade preponderante, escolha "Bares e restaurantes"`);
  if (nat.startsWith('2143')) avisos.push('a empresa é cooperativa: se optou pelo regime específico, as operações com associados podem ter alíquota zero (LC 214/2025, art. 271 — cClassTrib 200020/200054); confira essas notas');
  return { regime: '', origem: `CNAE principal ${fmt(pri)}${priDesc ? ' – ' + priDesc : ''}`, aviso: avisos.join(' · ') };
}
ipcMain.handle('fiscal:rtcAnalisar', async (_evt, { xmls, sped, regime }) => {
  if (!Array.isArray(xmls) || !xmls.length) return { error: 'Selecione os .zip com os XMLs.' };
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_rtc_${stamp}.json`);
  const htmlOut = path.join(os.tmpdir(), `fc_rtc_${stamp}.html`);
  const auto = regime === 'auto';
  const base = ['apuracao-rtc', '--xmls', ...xmls];
  if (sped) base.push('--sped', sped);
  let args = [...base];
  if (regime && !auto) args.push('--regime', String(regime).replace(/\D/g, ''));
  try {
    await runFiscal([...args, '--json', jsonOut, '--html', htmlOut], jsonOut);
    let res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    // "identificar pelo CNAE": consulta o cadastro do CNPJ da empresa (o mesmo cache da Legalização) e, se a atividade
    // principal tiver regime específico, refaz a apuração com ele
    let atividade = null;
    if (auto && res.cnpj) {
      try { atividade = _atividadeRtc(await _cnpjApiCache(res.cnpj)); } catch (_) { atividade = null; }
      if (!atividade) atividade = { regime: '', origem: '', aviso: 'Não foi possível consultar o CNAE na Receita agora: apuração feita como atividade geral.' };
      if (atividade.regime) {
        args = [...base, '--regime', atividade.regime];
        await runFiscal([...args, '--json', jsonOut, '--html', htmlOut], jsonOut);
        res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
        if (res.erro) return { error: res.erro };
      }
    }
    const html = fs.readFileSync(htmlOut, 'utf-8');
    if (_rtcUltimo && _rtcUltimo.html && _rtcUltimo.html !== htmlOut) fs.unlink(_rtcUltimo.html, () => {});
    _rtcUltimo = { args, html: htmlOut, nome: res.empresa || res.cnpj || '' };
    _biRegistrar('apuracao', res);
    return { ok: true, res, html, atividade };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('fiscal:rtcExportar', async (_evt, { formato }) => {
  if (!_rtcUltimo) return { error: 'Calcule a apuração primeiro.' };
  const ext = formato === 'xlsx' ? 'xlsx' : 'html';
  const base = `Apuracao-IBS-CBS-${String(_rtcUltimo.nome || '').replace(/[^\w-]+/g, '_')}`.replace(/_+$/, '');
  const r = await dialog.showSaveDialog(mainWindow, { title: ext === 'xlsx' ? 'Salvar Excel' : 'Salvar HTML',
    defaultPath: `${base}.${ext}`, filters: [{ name: ext === 'xlsx' ? 'Planilha Excel' : 'Página HTML', extensions: [ext] }] });
  if (r.canceled || !r.filePath) return { canceled: true };
  try {
    if (ext === 'html') fs.copyFileSync(_rtcUltimo.html, r.filePath);
    else {
      const jsonOut = path.join(os.tmpdir(), `fc_rtcx_${Date.now()}.json`);
      await runFiscal([..._rtcUltimo.args, '--json', jsonOut, '--xlsx', r.filePath], jsonOut);
      const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
      if (res.erro) return { error: res.erro };
    }
    shell.openPath(r.filePath);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- Inutilizadas × Domínio (equipe)
// Explica a numeração faltante do relatório "Notas não lançadas" do Domínio: consulta de inutilização do Portal Nacional da NF-e
// (CNPJ + ano; a pessoa marca o "Sou humano" — o sistema não resolve CAPTCHA — e o sistema lê a lista inteira) e SPED do cliente.
const INUT_URL = 'https://www.nfe.fazenda.gov.br/portal/consulta.aspx?tipoConsulta=inutilizacao&tipoConteudo=nDmpH/MjKrg=';
let _inutUltimo = null;   // { args, html, nome }
let _inutJanela = null;
ipcMain.handle('fiscal:inutPickDominio', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Relatório do Domínio "Notas não lançadas" (PDF)',
    properties: ['openFile'], filters: [{ name: 'PDF', extensions: ['pdf'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
ipcMain.handle('fiscal:inutPickSped', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'SPED Fiscal do cliente (um ou mais meses)',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});
// script injetado no portal: preenche CNPJ e ano, mostra o aviso e, depois do "Continuar", lê a tabela de inutilizações
const _INUT_JS_PREENCHE = (cnpj, ano, aviso, formatado) => `(() => {
  const vis = (e) => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const ev = (el) => ['input', 'change', 'blur'].forEach((t) => el.dispatchEvent(new Event(t, { bubbles: true })));
  let inp = [...document.querySelectorAll('input')].filter((i) => vis(i) && /text|^$/.test(i.type || '') && /cnpj/i.test(i.id + ' ' + i.name))[0];
  if (!inp) {
    const lab = [...document.querySelectorAll('label, span, td, div, p')].find((x) => /^\\s*CNPJ do Emitente\\s*:?\\s*\\*?\\s*$/i.test(x.innerText || ''));
    if (lab) inp = [...document.querySelectorAll('input')].find((i) => vis(i) && (lab.compareDocumentPosition(i) & 4) && /text|^$/.test(i.type || ''));
  }
  const sels = [...document.querySelectorAll('select')].filter((x) => vis(x) && [...x.options].some((o) => o.text.trim() === '${ano}'));
  const sel = sels.find((x) => /ano/i.test(x.id + ' ' + x.name)) || sels[0];
  if (inp && !inp.value) { inp.value = (${formatado ? 'true' : 'false'} && !(inp.maxLength > 0 && inp.maxLength < 18)) ? '${cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')}' : '${cnpj}'; ev(inp); }
  if (sel) { const o = [...sel.options].find((o) => o.text.trim() === '${ano}'); if (o && sel.value !== o.value) { sel.value = o.value; ev(sel); } }
  if (!document.getElementById('fcInutAviso')) {
    const d = document.createElement('div'); d.id = 'fcInutAviso';
    d.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:99999;background:#1f2a5a;color:#fff;font:600 14px Segoe UI,Arial;padding:10px 16px;text-align:center;box-shadow:0 4px 14px rgba(0,0,0,.25)';
    d.textContent = ${JSON.stringify(aviso)};
    document.body.appendChild(d);
  }
  return { cnpj: !!inp, ano: !!sel };
})()`;
const _INUT_JS_LE = `(() => {
  const tabs = [...document.querySelectorAll('table')].filter((t) => /Protocolo/i.test(t.innerText) && /N[uú]mero\\s+Inicial/i.test(t.innerText));
  if (!tabs.length) return { ok: false, vazio: /nenhum|n[ãa]o\\s+(foram\\s+)?encontrad/i.test(document.body.innerText || '') && /Nova Consulta/i.test(document.body.innerText || '') };
  const t = tabs.sort((a, b) => a.innerText.length - b.innerText.length)[0];
  const linhas = [];
  [...t.querySelectorAll('tr')].forEach((tr) => {
    const c = [...tr.querySelectorAll('td')].map((td) => td.innerText.trim());
    if (c.length >= 7 && /^\\d{1,4}$/.test(c[0]) && /^\\d+$/.test(c[3]) && /^\\d+$/.test(c[4])) {
      linhas.push({ ano: c[0], modelo: c[1], serie: c[2], ini: c[3], fim: c[4], protocolo: c[5], data: c[6], receb: c[7] || '' });
    }
  });
  // paginação do portal (se houver): próximo número de página depois do atual
  const pag = [...t.querySelectorAll('a')].filter((a) => /^\\d+$|^\\.\\.\\.$|^>$|pr[óo]xim/i.test(a.innerText.trim()));
  const atual = [...t.querySelectorAll('span, td')].map((x) => x.innerText.trim()).find((x, i, arr) => /^\\d+$/.test(x) && x.length < 4 && !x.includes(' ') && false);
  // CNPJ do cabeçalho do resultado: 14 dígitos com qualquer separador (o portal pode usar traço longo, espaço etc.)
  const mc = (document.body.innerText || '').match(/CNPJ[^\\d\\n]{0,15}((?:\\d[^\\d\\n]{0,3}){13}\\d)/);
  const cnpj = mc ? mc[1].replace(/\\D/g, '') : '';
  return { ok: true, linhas, paginas: pag.map((a) => a.innerText.trim()), cnpj, primeiro: linhas[0] ? linhas[0].protocolo : '' };
})()`;
// leitor genérico (portal da NFC-e da SEFIN-RO): acha a tabela pelo cabeçalho (Protocolo + Número/Série) e mapeia as colunas pelo nome
const _INUT_JS_LE_GEN = (ano) => `(() => {
  const norm = (s) => String(s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
  const dig = (s) => String(s || '').replace(/[^\\d]/g, '');
  const corpo = document.body ? document.body.innerText || '' : '';
  const mapa = (cab) => {
    const m = {};
    cab.forEach((h, i) => {
      const t = norm(h);
      if (m.protocolo === undefined && /protocolo/.test(t)) m.protocolo = i;
      else if (m.ini === undefined && /inicial|inicio|^de$|num.*ini/.test(t)) m.ini = i;
      else if (m.fim === undefined && /final|^fim|^ate$|num.*fin/.test(t)) m.fim = i;
      else if (m.serie === undefined && /serie/.test(t)) m.serie = i;
      else if (m.modelo === undefined && /modelo|^mod\\.?$/.test(t)) m.modelo = i;
      else if (m.ano === undefined && /^ano$/.test(t)) m.ano = i;
      else if (m.data === undefined && /data|hora|^dt/.test(t) && !/recebimento/.test(t)) m.data = i;
      else if (m.num === undefined && /^(numero|n[oº°]\\.?|num\\.?|numeracao|faixa)$/.test(t)) m.num = i;
    });
    return m;
  };
  const linhas = [];
  for (const t of document.querySelectorAll('table')) {
    const trs = [...t.querySelectorAll('tr')];
    const hi = trs.findIndex((tr) => { const x = norm(tr.innerText); return /protocolo/.test(x) && /numero|inicial|serie|faixa/.test(x) && tr.querySelectorAll('td, th').length >= 3; });
    if (hi < 0) continue;
    const m = mapa([...trs[hi].querySelectorAll('th, td')].map((c) => c.innerText));
    if (m.protocolo === undefined || (m.ini === undefined && m.num === undefined)) continue;
    trs.slice(hi + 1).forEach((tr) => {
      const c = [...tr.querySelectorAll('td')].map((td) => td.innerText.trim());
      if (c.length < 3) return;
      let ini = '', fim = '';
      const base = m.ini !== undefined ? c[m.ini] : c[m.num];
      const faixa = String(base || '').match(/(\\d[\\d.]*)\\s*(?:a|at[eé]|-|–|\\/)\\s*(\\d[\\d.]*)/i);
      if (faixa) { ini = dig(faixa[1]); fim = dig(faixa[2]); }
      else { ini = dig(base); fim = m.fim !== undefined ? dig(c[m.fim]) : ini; }
      if (!ini) return;
      const data = m.data !== undefined ? c[m.data] : '';
      let a = m.ano !== undefined ? dig(c[m.ano]) : '';
      if (!a) { const y = String(data).match(/(20\\d\\d)/); a = y ? y[1] : '${ano}'; }
      linhas.push({ ano: a, modelo: (m.modelo !== undefined && dig(c[m.modelo])) || '65', serie: m.serie !== undefined ? dig(c[m.serie]) : '',
        ini, fim: fim || ini, protocolo: dig(c[m.protocolo]) || c[m.protocolo], data, receb: '' });
    });
    if (linhas.length) break;
  }
  if (!linhas.length) {
    // sem tabela: resultado em pares "rótulo: valor" (um ou mais registros)
    const pega = (re) => [...corpo.matchAll(re)].map((x) => x[1].trim());
    const prot = pega(/Protocolo[^:\\n]{0,25}:\\s*(\\d{10,20})/gi);
    const ini = pega(/N[uú]mero\\s+Inicial[^:\\n]{0,10}:\\s*(\\d[\\d.]*)/gi);
    const fim = pega(/N[uú]mero\\s+Final[^:\\n]{0,10}:\\s*(\\d[\\d.]*)/gi);
    const ser = pega(/S[ée]rie[^:\\n]{0,10}:\\s*(\\d+)/gi);
    const dat = pega(/Data[^:\\n]{0,30}:\\s*([\\d\\/]{8,10}(?:\\s+[\\d:]{5,8})?)/gi);
    prot.forEach((p, i) => {
      if (!ini[i]) return;
      const y = String(dat[i] || '').match(/(20\\d\\d)/);
      linhas.push({ ano: y ? y[1] : '${ano}', modelo: '65', serie: ser[i] || '', ini: dig(ini[i]), fim: dig(fim[i] || ini[i]), protocolo: p, data: dat[i] || '', receb: '' });
    });
  }
  if (linhas.length) return { ok: true, linhas, paginas: [], cnpj: '', primeiro: linhas[0].protocolo + '|' + linhas.length };
  const n = norm(corpo);
  return { ok: false, vazio: /nenhum(a)? (registro|inutiliza|resultado|numeracao)|nao (foi|foram) encontrad|nao (ha|existe|existem) (registro|inutiliza|numeracao)|sem (registro|inutiliza)|nao possui (registro|inutiliza)/.test(n),
    erroCaptcha: /captcha|codigo (da imagem )?(invalido|incorreto)/.test(n) && /invalid|incorret|errad/.test(n) };
})()`;
const INUT_FONTES = {
  nfe: { url: INUT_URL, titulo: 'Consultar Inutilização (Portal Nacional da NF-e)', particao: 'persist:portal-nfe', formatado: false,
    aviso: 'FiscoCont+: confira o CNPJ e o ano, marque "Sou humano" e clique em Continuar. A lista de inutilizações é lida sozinha e esta janela fecha.',
    le: () => _INUT_JS_LE },
  'nfce-ro': { url: 'https://www.nfce.sefin.ro.gov.br/consultarInutilizado.jsp', titulo: 'Consultar Inutilização (Portal da NFC-e · SEFIN-RO)', particao: 'persist:portal-nfce-ro', formatado: true,
    aviso: 'FiscoCont+: confira o CNPJ e o ano, digite o código da imagem (Captcha) e clique em Consultar. As inutilizações de NFC-e são lidas sozinhas e esta janela fecha.',
    le: (ano) => _INUT_JS_LE_GEN(ano) },
};
ipcMain.handle('fiscal:inutPortal', async (_evt, { cnpj, ano, fonte }) => {
  const F = INUT_FONTES[fonte] || INUT_FONTES.nfe; fonte = INUT_FONTES[fonte] ? fonte : 'nfe';
  cnpj = String(cnpj || '').replace(/\D/g, ''); ano = String(ano || new Date().getFullYear());
  if (cnpj.length !== 14) return { error: 'CNPJ inválido.' };
  if (_inutJanela && !_inutJanela.isDestroyed()) { _inutJanela.focus(); return { error: 'A janela do portal já está aberta.' }; }
  const w = new BrowserWindow({ parent: mainWindow, width: 1150, height: 820, title: `FiscoCont+ · ${F.titulo}`, autoHideMenuBar: true,
    webPreferences: { partition: F.particao, contextIsolation: true, nodeIntegration: false, sandbox: true } });
  _inutJanela = w;
  w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  const js = (c) => Promise.race([w.webContents.executeJavaScript(c, true), new Promise((_r, rej) => setTimeout(() => rej(new Error('sem resposta')), 15000))]);
  return new Promise((resolve) => {
    let fim = false, timer = null, todas = [], vistos = new Set(), paginasFeitas = new Set(['1']), ultimoPrimeiro = '', cargas = 0, vazioAntes = null;
    const acaba = (r) => { if (fim) return; fim = true; clearInterval(timer); try { if (!w.isDestroyed()) w.close(); } catch (_) {} _inutJanela = null; resolve(r && r.ok ? { ...r, fonte } : r); };
    w.on('closed', () => acaba(todas.length ? { ok: true, linhas: todas, ano, cnpj } : { canceled: true }));
    w.webContents.on('did-finish-load', () => { cargas++; js(_INUT_JS_PREENCHE(cnpj, ano, F.aviso, F.formatado)).catch(() => {}); });
    w.loadURL(F.url).catch(() => {});
    const t0 = Date.now();
    timer = setInterval(async () => {
      if (fim || w.isDestroyed()) return;
      if (Date.now() - t0 > 15 * 60 * 1000) return acaba(todas.length ? { ok: true, linhas: todas, ano, cnpj } : { error: 'A consulta não foi concluída em 15 minutos.' });
      let r;
      try { r = await js(F.le(ano)); } catch (_) { return; }
      if (!r) return;
      if (!r.ok) {
        // "nenhuma inutilização" só vale depois da consulta (página recarregada, ou a mensagem apareceu agora)
        if (vazioAntes === null) vazioAntes = !!r.vazio;
        if (r.vazio && !r.erroCaptcha && (cargas >= 2 || !vazioAntes)) acaba({ ok: true, linhas: [], ano, cnpj, vazio: true });
        return;
      }
      if (r.cnpj && r.cnpj.length === 14 && r.cnpj !== cnpj) return acaba({ error: `O portal mostrou o CNPJ ${r.cnpj}, diferente do CNPJ do relatório do Domínio (${cnpj}).` });
      if (r.primeiro === ultimoPrimeiro) return;           // mesma página ainda
      ultimoPrimeiro = r.primeiro;
      r.linhas.forEach((l) => { const k = `${l.modelo}|${l.serie}|${l.ini}|${l.fim}|${l.protocolo}`; if (!vistos.has(k)) { vistos.add(k); todas.push(l); } });
      // próxima página, se o portal paginar
      const prox = (r.paginas || []).find((p) => /^\d+$/.test(p) && !paginasFeitas.has(p));
      if (prox) {
        paginasFeitas.add(prox);
        try { await js(`(() => { const a = [...document.querySelectorAll('table a')].find((a) => a.innerText.trim() === '${prox}'); if (a) a.click(); return !!a; })()`); } catch (_) {}
        return;
      }
      acaba({ ok: true, linhas: todas, ano, cnpj });
    }, 1500);
  });
});
ipcMain.handle('fiscal:inutConferir', async (_evt, { dominio, portal, speds }) => {
  if (!dominio) return { error: 'Selecione o relatório "Notas não lançadas" do Domínio.' };
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_inut_${stamp}.json`);
  const htmlOut = path.join(os.tmpdir(), `fc_inut_${stamp}.html`);
  const args = ['inutilizadas', '--dominio', dominio];
  if (portal && (Array.isArray(portal) ? portal.length : portal.consultado)) {
    const pj = path.join(os.tmpdir(), `fc_inut_portal_${stamp}.json`);
    fs.writeFileSync(pj, JSON.stringify(portal), 'utf-8');
    args.push('--portal', pj);
  }
  if (Array.isArray(speds) && speds.length) args.push('--sped', ...speds);
  try {
    await runFiscal([...args, '--json', jsonOut, '--html', htmlOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    const html = fs.readFileSync(htmlOut, 'utf-8');
    if (_inutUltimo && _inutUltimo.html && _inutUltimo.html !== htmlOut) fs.unlink(_inutUltimo.html, () => {});
    _inutUltimo = { args, html: htmlOut, nome: res.empresa || res.cnpj || '' };
    return { ok: true, res, html };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('fiscal:inutExportar', async () => {
  if (!_inutUltimo) return { error: 'Faça a conferência primeiro.' };
  const base = `Inutilizadas-Dominio-${String(_inutUltimo.nome || '').replace(/[^\w-]+/g, '_')}`.replace(/_+$/, '');
  const r = await dialog.showSaveDialog(mainWindow, { title: 'Salvar Excel', defaultPath: `${base}.xlsx`, filters: [{ name: 'Planilha Excel', extensions: ['xlsx'] }] });
  if (r.canceled || !r.filePath) return { canceled: true };
  try {
    const jsonOut = path.join(os.tmpdir(), `fc_inutx_${Date.now()}.json`);
    await runFiscal([..._inutUltimo.args, '--json', jsonOut, '--xlsx', r.filePath], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    shell.openPath(r.filePath);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('admin:audPick', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione a EFD ICMS/IPI (SPED Fiscal) do cliente do Amazonas',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});

// ---------------------------------------------------------------- Análise Tributária (liberada para a equipe; só lê o SPED)
// Tributação das entradas por produto + auditoria de tributação (ST de RO, alíquota, crédito, DIFAL, combustível, PIS/COFINS).
let _atribUltimo = null;   // { sped, html }
ipcMain.handle('admin:atribPick', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione o SPED Fiscal (EFD ICMS/IPI) para a auditoria das entradas',
    properties: ['openFile'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
ipcMain.handle('admin:atribAnalisar', async (_evt, { sped }) => {
  if (!sped) return { error: 'Selecione o SPED Fiscal.' };
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_atrib_${stamp}.json`);
  const htmlOut = path.join(os.tmpdir(), `fc_atrib_${stamp}.html`);
  try {
    await runFiscal(['aud-tributacao', '--sped', sped, '--json', jsonOut, '--html', htmlOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    const html = fs.readFileSync(htmlOut, 'utf-8');
    if (_atribUltimo && _atribUltimo.html && _atribUltimo.html !== htmlOut) fs.unlink(_atribUltimo.html, () => {});
    _atribUltimo = { sped, html: htmlOut };
    _biRegistrar('analise', res);
    return { ok: true, res, html };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:atribExportar', async (_evt, { formato, nome }) => {
  if (!_atribUltimo) return { error: 'Rode a auditoria primeiro.' };
  const ext = formato === 'xlsx' ? 'xlsx' : 'html';
  const base = `Tributacao-Entradas-${String(nome || '').replace(/[^\w-]+/g, '_')}`.replace(/_+$/, '');
  const r = await dialog.showSaveDialog(mainWindow, { title: ext === 'xlsx' ? 'Salvar Excel detalhado' : 'Salvar HTML animado',
    defaultPath: `${base}.${ext}`, filters: [{ name: ext === 'xlsx' ? 'Planilha Excel' : 'Página HTML', extensions: [ext] }] });
  if (r.canceled || !r.filePath) return { canceled: true };
  try {
    if (ext === 'html') fs.copyFileSync(_atribUltimo.html, r.filePath);
    else {
      const jsonOut = path.join(os.tmpdir(), `fc_atribx_${Date.now()}.json`);
      await runFiscal(['aud-tributacao', '--sped', _atribUltimo.sped, '--json', jsonOut, '--xlsx', r.filePath], jsonOut);
      const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
      if (res.erro) return { error: res.erro };
    }
    shell.openPath(r.filePath);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('admin:audAnalisar', async (_evt, { sped }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!sped || !sped.length) return { error: 'Selecione ao menos um SPED Fiscal.' };
  const jsonOut = path.join(os.tmpdir(), `fc_audam_${Date.now()}.json`);
  try {
    await runFiscal(['auditoria-icms-am', '--sped', ...sped, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- Evolução Tributária (Admin)
// Tabela 5.1.1 (códigos de ajuste do E111) da UF do SPED, baixada do serviço oficial de Tabelas Externas do Sped
// e guardada no computador (renovada a cada 15 dias). Sem internet, o núcleo usa a cópia embutida (AM e RO)
// ou a descrição complementar do próprio E111.
const SPED_TABELAS = 'http://www.sped.fazenda.gov.br/spedtabelas';
const UF_NOMES = { AC: 'Acre', AL: 'Alagoas', AP: 'Amapá', AM: 'Amazonas', BA: 'Bahia', CE: 'Ceará', DF: 'Distrito Federal', ES: 'Espírito Santo',
  GO: 'Goiás', MA: 'Maranhão', MT: 'Mato Grosso', MS: 'Mato Grosso do Sul', MG: 'Minas Gerais', PA: 'Pará', PB: 'Paraíba', PR: 'Paraná',
  PE: 'Pernambuco', PI: 'Piauí', RJ: 'Rio de Janeiro', RN: 'Rio Grande do Norte', RS: 'Rio Grande do Sul', RO: 'Rondônia', RR: 'Roraima',
  SC: 'Santa Catarina', SP: 'São Paulo', SE: 'Sergipe', TO: 'Tocantins' };
function _ufDoSped(arq) {
  try {
    const fd = fs.openSync(arq, 'r'); const buf = Buffer.alloc(600); const n = fs.readSync(fd, buf, 0, 600, 0); fs.closeSync(fd);
    const c = buf.slice(0, n).toString('latin1').split(/\r?\n/)[0].split('|');
    return c[1] === '0000' ? (c[9] || '').trim() : '';
  } catch (_) { return ''; }
}
async function _getTexto(url, ms) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), ms || 15000);
  try {
    const resp = await (net && net.fetch ? net.fetch(url, { signal: ctrl.signal }) : fetch(url, { signal: ctrl.signal }));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const buf = Buffer.from(await resp.arrayBuffer());
    const u = buf.toString('utf-8');
    return u.includes('�') ? buf.toString('latin1') : u;
  } finally { clearTimeout(t); }
}
async function _tabelaAjustesUF(uf) {
  if (!UF_NOMES[uf]) return null;
  const dir = path.join(app.getPath('userData'), 'tabelas-sped');
  const arq = path.join(dir, `5.1.1-${uf}.txt`);
  try { if (Date.now() - fs.statSync(arq).mtimeMs < 15 * 864e5) return arq; } catch (_) {}
  try {
    let lista = await _getTexto(`${SPED_TABELAS}/WsConsulta/WsConsulta.asmx/consultarVersoesTabelasExternas?codigoSistema=SpedFiscal`);
    lista = lista.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    const partes = lista.split(/desc="(Tabelas d[aoe]s? [^"]+)"/);
    let alvo = null;
    for (let k = 1; k < partes.length; k += 2) {
      const nome = partes[k].replace(/^Tabelas d[aoe]s? /, '').trim();
      if (nome !== UF_NOMES[uf]) continue;
      const m = partes[k + 1].match(/<tabela id="(\d+)" tipo="AJ_APUR_DED"[^>]*versao="(\d+)"/);
      if (m) alvo = { id: m[1], versao: m[2] };
      break;
    }
    if (!alvo) return fs.existsSync(arq) ? arq : null;
    const txt = await _getTexto(`${SPED_TABELAS}/wsconsulta/obterTabela.ashx?idTabela=${alvo.id}&versao=${alvo.versao}`);
    if (!/\|/.test(txt)) throw new Error('tabela vazia');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(arq, txt, 'utf-8');
    return arq;
  } catch (_) {
    return fs.existsSync(arq) ? arq : null;   // sem internet: usa a última cópia baixada, se houver
  }
}

ipcMain.handle('admin:evoPick', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione os SPED Fiscais (EFD ICMS/IPI) do período — um por mês, da mesma empresa',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});

// Conteúdo do painel (CSS + JS) para embutir no HTML do cliente — lido aqui porque o renderer não pode dar fetch em file://
ipcMain.handle('admin:evoAssets', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  try {
    const dir = path.join(__dirname, '..', 'renderer');
    return { css: fs.readFileSync(path.join(dir, 'evolucao.css'), 'utf-8'), js: fs.readFileSync(path.join(dir, 'evolucao_dash.js'), 'utf-8') };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('admin:evoAnalisar', async (_evt, { sped }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!sped || !sped.length) return { error: 'Selecione os SPED Fiscais do período.' };
  const jsonOut = path.join(os.tmpdir(), `fc_evo_${Date.now()}.json`);
  try {
    const uf = _ufDoSped(sped[sped.length - 1]);
    const tabela = uf ? await _tabelaAjustesUF(uf) : null;
    const args = ['evolucao-tributaria', '--sped', ...sped, '--json', jsonOut];
    if (tabela) args.push('--tabela', tabela);
    await runFiscal(args, jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('admin:radarStatus', async (_evt, { chave, status, nota }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const st = _jsonUser('radar-status.json', {});
  st[chave] = { status, nota: nota || '', em: new Date().toISOString() };
  try { _salvarJsonUser('radar-status.json', st); return { ok: true, status: st }; }
  catch (e) { return { error: String(e.message || e) }; }
});

async function _rodarLegalizacao(cnpj, comHtml) {
  const base = _jsonUser('legalizacao.json', { clientes: {} });
  const cli = base.clientes[cnpj];
  if (!cli || !cli.api) return { error: 'Consulte o CNPJ primeiro.' };
  const stamp = Date.now();
  const apiP = path.join(os.tmpdir(), `fc_leg_api_${stamp}.json`);
  const estP = path.join(os.tmpdir(), `fc_leg_est_${stamp}.json`);
  const outP = path.join(os.tmpdir(), `fc_leg_out_${stamp}.json`);
  const htmlP = path.join(os.tmpdir(), `fc_leg_${stamp}.html`);
  fs.writeFileSync(apiP, JSON.stringify(cli.api), 'utf-8');
  fs.writeFileSync(estP, JSON.stringify({ itens: cli.itens || {} }), 'utf-8');
  const args = ['legalizacao-levantamento', '--api', apiP, '--estado', estP, '--json', outP];
  if (comHtml) args.push('--html', htmlP);
  await runFiscal(args, outP);
  const res = JSON.parse(fs.readFileSync(outP, 'utf-8'));
  let html = null;
  if (comHtml && fs.existsSync(htmlP)) html = fs.readFileSync(htmlP, 'utf-8');
  [apiP, estP, outP, htmlP].forEach((p) => fs.unlink(p, () => {}));
  if (res.erro) return { error: res.erro };
  return { ok: true, res, html, itens: cli.itens || {}, consultadoEm: cli.consultadoEm };
}

ipcMain.handle('admin:legalLista', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const base = _jsonUser('legalizacao.json', { clientes: {} });
  const lista = Object.entries(base.clientes).map(([cnpj, c]) => ({ cnpj, nome: (c.api && c.api.razao_social) || cnpj, consultadoEm: c.consultadoEm }));
  lista.sort((a, b) => String(b.consultadoEm || '').localeCompare(String(a.consultadoEm || '')));
  return { ok: true, lista };
});

ipcMain.handle('admin:legalConsultar', async (_evt, { cnpj, usarCache }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const dig = String(cnpj || '').replace(/\D/g, '');
  if (dig.length !== 14) return { error: 'Informe um CNPJ com 14 dígitos.' };
  const base = _jsonUser('legalizacao.json', { clientes: {} });
  try {
    if (!(usarCache && base.clientes[dig] && base.clientes[dig].api)) {
      let api;
      const fontes = [
        `https://brasilapi.com.br/api/cnpj/v1/${dig}`,
        `https://minhareceita.org/${dig}`
      ];
      const hdrs = {
        Accept: 'application/json',
        'Accept-Language': 'pt-BR,pt;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 FiscoContPlus'
      };
      let ultimoErro = '';
      let naoEncontrado = false;
      for (const url of fontes) {
        for (let tent = 0; tent < 2 && !api; tent++) {
          try {
            // net.fetch usa a rede do Chromium (mesma pilha do navegador), que passa melhor por firewalls de API
            const resp = await (net && net.fetch ? net.fetch(url, { headers: hdrs }) : fetch(url, { headers: hdrs }));
            if (resp.status === 404) { naoEncontrado = true; break; }
            if (resp.ok) { api = await resp.json(); break; }
            ultimoErro = `HTTP ${resp.status}`;
            if (resp.status !== 429 && resp.status < 500) break;
          } catch (e) { ultimoErro = String(e.message || e); }
          await new Promise(r => setTimeout(r, 1200));
        }
        if (api) break;
      }
      if (!api) {
        if (naoEncontrado) return { error: 'CNPJ não encontrado na base da Receita.' };
        return { error: `A consulta falhou (${ultimoErro || 'sem resposta'}). Verifique a internet e tente de novo em instantes.` };
      }
      const antigo = base.clientes[dig] || {};
      base.clientes[dig] = { api, itens: antigo.itens || {}, consultadoEm: new Date().toISOString() };
      _salvarJsonUser('legalizacao.json', base);
    }
    return await _rodarLegalizacao(dig, false);
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('admin:legalSalvar', async (_evt, { cnpj, itens, html }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const dig = String(cnpj || '').replace(/\D/g, '');
  const base = _jsonUser('legalizacao.json', { clientes: {} });
  if (!base.clientes[dig]) return { error: 'Consulte o CNPJ primeiro.' };
  try {
    base.clientes[dig].itens = itens || {};
    _salvarJsonUser('legalizacao.json', base);
    return await _rodarLegalizacao(dig, !!html);
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---- Correção do SPED Fiscal (restrito ao Admin) ----
let lastSpedCorrigidoPath = null;
let lastSpedLmcPath = null;

ipcMain.handle('fiscal:visualizarSped', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const htmlOut = path.join(os.tmpdir(), `fc_viz_${Date.now()}.html`);
  try {
    await runFiscal(['visualizar-sped', spedPath, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
    return { ok: true, html };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:corrigirSped', async (_evt, { spedPath, cestInvalidos, usarCorrigido }) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  // encadeia com o que já foi aplicado nesta sessão (DIFAL, crédito, Simples): corrige em cima do arquivo já corrigido
  const base = _difalBase(spedPath, usarCorrigido);
  const saidaTmp = path.join(os.tmpdir(), `fc_corrigido_${Date.now()}.txt`);
  const resumoTmp = path.join(os.tmpdir(), `fc_resumo_${Date.now()}.json`);
  try {
    const cestArg = (cestInvalidos || []).filter(Boolean).join(',');
    const htmlTmp = path.join(os.tmpdir(), `fc_corr_dash_${Date.now()}.html`);
    const args = ['corrigir', base.arq, '--saida', saidaTmp, '--html', htmlTmp, '--json', resumoTmp];
    if (cestArg) args.push('--cest', cestArg);
    // o .json é o último arquivo gravado pelo núcleo: esperar por ele garante SPED e dashboard completos
    await runFiscal(args, resumoTmp);
    const resumo = JSON.parse(fs.readFileSync(resumoTmp, 'utf-8'));
    fs.unlink(resumoTmp, () => {});
    let html = '';
    try { html = fs.readFileSync(htmlTmp, 'utf-8'); fs.unlink(htmlTmp, () => {}); } catch (_) {}
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== saidaTmp) fs.unlink(lastSpedCorrigidoPath, () => {});
    lastSpedCorrigidoPath = saidaTmp;
    lastCorretorDash = { spedPath, html };
    return { ok: true, resumo, html, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---------------------------------------------------------------- Regime da empresa (Simples Nacional) pelo CNPJ do SPED
// O SPED não informa se a empresa é do Simples. O DIFAL de RO muda com isso (Lei 688/96, art. 18, § 9º — base única
// desde 11/06/2025), então o CNPJ do 0000 é consultado na Receita (BrasilAPI / minhareceita) e o resultado fica guardado
// em legalizacao.json (o mesmo cache da Legalização) por 30 dias.
async function _consultaCnpjApi(dig) {
  const fontes = [`https://brasilapi.com.br/api/cnpj/v1/${dig}`, `https://minhareceita.org/${dig}`];
  const hdrs = { Accept: 'application/json', 'User-Agent': 'Mozilla/5.0 FiscoContPlus' };
  for (const url of fontes) {
    for (let tent = 0; tent < 2; tent++) {
      try {
        const op = { headers: hdrs, signal: AbortSignal.timeout(8000) };
        const resp = await (net && net.fetch ? net.fetch(url, op) : fetch(url, op));
        if (resp.status === 404) return null;
        if (resp.ok) return await resp.json();
        if (resp.status !== 429 && resp.status < 500) break;
      } catch (_) { /* tenta de novo / próxima fonte */ }
      await new Promise(r => setTimeout(r, 1000));
    }
  }
  return null;
}
function _cab0000(arq) {
  try {
    const fd = fs.openSync(arq, 'r'); const buf = Buffer.alloc(600);
    const n = fs.readSync(fd, buf, 0, 600, 0); fs.closeSync(fd);
    const c = buf.slice(0, n).toString('latin1').split(/\r?\n/)[0].split('|');
    if (c[1] !== '0000') return null;
    return { cnpj: String(c[7] || '').replace(/\D/g, ''), dtIni: c[4] || '', dtFin: c[5] || '' };
  } catch (_) { return null; }
}
function _isoDeSped(d) { return /^\d{8}$/.test(d || '') ? `${d.slice(4)}-${d.slice(2, 4)}-${d.slice(0, 2)}` : ''; }
function _brDeIso(d) { return /^\d{4}-\d{2}-\d{2}/.test(d || '') ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : ''; }
// cadastro público do CNPJ (BrasilAPI / minhareceita), guardado 30 dias em legalizacao.json
async function _cnpjApiCache(cnpj) {
  cnpj = String(cnpj || '').replace(/\D/g, '');
  if (cnpj.length !== 14) return null;
  const base = _jsonUser('legalizacao.json', { clientes: {} });
  const cache = base.clientes[cnpj];
  let api = cache && cache.api;
  const velho = !cache || !cache.consultadoEm || (Date.now() - Date.parse(cache.consultadoEm)) > 30 * 86400000;
  if (!api || velho) {
    const novo = await _consultaCnpjApi(cnpj);
    if (novo) {
      api = novo;
      base.clientes[cnpj] = { ...(cache || {}), api, itens: (cache && cache.itens) || {}, consultadoEm: new Date().toISOString() };
      try { _salvarJsonUser('legalizacao.json', base); } catch (_) {}
    }
  }
  return api || null;
}
async function _regimeDoCnpj(cnpj, dtIni, dtFin) {
  if (!cnpj || cnpj.length !== 14) return null;
  const api = await _cnpjApiCache(cnpj);
  if (!api) return null;
  const ini = _isoDeSped(dtIni), fim = _isoDeSped(dtFin);
  const op = String(api.data_opcao_pelo_simples || '').slice(0, 10);
  const ex = String(api.data_exclusao_do_simples || '').slice(0, 10);
  let simples;
  if (op) simples = (!fim || op <= fim) && (!ex || !ini || ex > ini);
  else simples = api.opcao_pelo_simples === true;
  let info = 'Receita Federal';
  if (simples) info = (op ? `optante desde ${_brDeIso(op)}` : 'optante') + (ex ? `, excluída em ${_brDeIso(ex)}` : '') + ' — Receita Federal';
  else if (ex) info = `excluída do Simples em ${_brDeIso(ex)} — Receita Federal`;
  return { regime: simples ? 'simples' : 'normal', info };
}
async function _regimesJson(arquivos) {
  const out = {};
  for (const arq of arquivos) {
    const cab = _cab0000(arq);
    if (!cab || out[cab.cnpj]) continue;
    const r = await _regimeDoCnpj(cab.cnpj, cab.dtIni, cab.dtFin);
    if (r) out[cab.cnpj] = r;
  }
  const p = path.join(os.tmpdir(), `fc_regimes_${Date.now()}.json`);
  fs.writeFileSync(p, JSON.stringify(out), 'utf-8');
  return p;
}
function _spedsDaPasta(pasta, prof = 0, out = []) {
  if (prof > 4 || out.length > 400) return out;
  let ents = [];
  try { ents = fs.readdirSync(pasta, { withFileTypes: true }); } catch (_) { return out; }
  for (const e of ents) {
    const p = path.join(pasta, e.name);
    if (e.isDirectory()) _spedsDaPasta(p, prof + 1, out);
    else if (/\.txt$/i.test(e.name) && _cab0000(p)) out.push(p);
  }
  return out;
}

// ---------------------------------------------------------------- Uso e consumo / ativo: CFOP e DIFAL de RO (Admin)
// Trabalha sobre o SPED escolhido no Corretor ou, se a correção geral já foi rodada, sobre o arquivo já corrigido.
function _difalBase(spedPath, usarCorrigido) {
  if (usarCorrigido && lastSpedCorrigidoPath && fs.existsSync(lastSpedCorrigidoPath)) return { arq: lastSpedCorrigidoPath, origem: 'corrigido' };
  return { arq: spedPath, origem: 'original' };
}
ipcMain.handle('admin:difalAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_difal_${Date.now()}.json`);
  try {
    const regimes = await _regimesJson([base.arq]);
    await runFiscal(['difal-ro', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--regimes', regimes, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(regimes, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:difalAplicar', async (_evt, { spedPath, usarCorrigido, selecao, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_difal_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_difal_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_difal_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    const regimes = await _regimesJson([base.arq]);
    await runFiscal(['difal-ro', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--regimes', regimes, '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {}); fs.unlink(regimes, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Acumulador genérico 7000 (DESPESAS) → acumulador de despesa certo (7001–7040), revisado pelo Admin — só Admin
// Memória do acumulador 7000 (nuvem, só Admin): descrição + NCM → acumulador escolhido, quem e quando. O produto
// que já foi decidido uma vez vem como "Confirmado por …" nos próximos arquivos, de qualquer cliente.
async function _memAcumLer() {
  try {
    const db = auth.db(); if (!db) return {};
    const f = auth.fsMod();
    const s = await f.getDoc(f.doc(db, 'memoria_admin', 'acum7000'));
    return s.exists() ? (s.data().m || {}) : {};
  } catch (_) { return {}; }
}
async function _memAcumGravar(lista) {
  const db = auth.db(); if (!db || !lista || !lista.length) return;
  const f = auth.fsMod();
  const ses = auth.sessao() || {};
  const hoje = new Date().toLocaleDateString('pt-BR');
  const upd = {};
  for (const x of lista.slice(0, 2000)) {
    if (!/^[0-9a-f]{20}$/.test(x.chave || '') || !/^70\d\d$/.test(x.a || '')) continue;
    upd[x.chave] = { a: x.a, p: ses.nome || ses.email || 'Admin', e: hoje, d: String(x.descr || '').slice(0, 80) };
  }
  if (Object.keys(upd).length) await f.setDoc(f.doc(db, 'memoria_admin', 'acum7000'), { m: upd }, { merge: true });
}
ipcMain.handle('admin:acum7000Analisar', async (_evt, { spedPath, usarCorrigido }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_acum_${Date.now()}.json`);
  const memJson = path.join(os.tmpdir(), `fc_acum_mem_${Date.now()}.json`);
  try {
    fs.writeFileSync(memJson, JSON.stringify(await _memAcumLer()), 'utf-8');
    await runFiscal(['acum-7000', '--sped', base.arq, '--json', jsonOut, '--memoria', memJson], jsonOut);
    fs.unlink(memJson, () => {});
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:acum7000Aplicar', async (_evt, { spedPath, usarCorrigido, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_acum_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_acum_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_acum_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['acum-7000', '--sped', base.arq, '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    try { await _memAcumGravar((selecao || {}).memoria || []); } catch (_) {}   // memória: falha não impede a correção
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// 🔎 Analisar tudo / Aplicar tudo (todas as conferências do Corretor num painel só) e Desconto × XML — só Admin
function _corrProg(evt, nome) {
  const arq = path.join(os.tmpdir(), `fc_prog_${nome}_${Date.now()}.json`);
  return { arq, cb: (d) => { try { if (!evt.sender.isDestroyed()) evt.sender.send('corr:progresso', d); } catch (_) {} } };
}
ipcMain.handle('admin:tudoAnalisar', async (evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_tudo_${Date.now()}.json`);
  try {
    const perm = await _corrPermitidas();
    const regimes = await _regimesJson([base.arq]);
    const prog = _corrProg(evt, 'tudo');
    await runFiscal(['analisar-tudo', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--regimes', regimes, '--json', jsonOut,
      '--progresso', prog.arq, ...(perm ? ['--etapas', perm.join(',')] : [])], jsonOut, prog);
    fs.unlink(prog.arq, () => {});
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {}); fs.unlink(regimes, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:tudoAplicar', async (evt, { spedPath, usarCorrigido, xmls, escolhas }) => {
  const bloq = _soCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const escJson = path.join(os.tmpdir(), `fc_tudo_esc_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_tudo_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_tudo_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(escJson, JSON.stringify(escolhas || {}), 'utf-8');
    const prog = _corrProg(evt, 'aplica');
    const perm = await _corrPermitidas();
    const regimes = await _regimesJson([base.arq]);
    await runFiscal(['analisar-tudo', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--regimes', regimes, '--json', jsonOut,
      '--aplicar', escJson, '--saida', saida, '--progresso', prog.arq, ...(perm ? ['--etapas', perm.join(',')] : [])], jsonOut, prog);
    fs.unlink(prog.arq, () => {});
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    for (const f of [jsonOut, escJson, regimes]) fs.unlink(f, () => {});
    if (res.precisa_e116) return { precisa_e116: true, error: res.erro };
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
// PDF ao cliente com o que foi alterado de fato no NCM (0200) — informativo, com a logo da Liddera
ipcMain.handle('admin:ncmPdf', async (_evt, { ncm } = {}) => {
  const bloq = _soCorretor(); if (bloq) return bloq;
  if (!ncm || !(ncm.feitos || []).length) return { error: 'Nenhum NCM foi alterado neste arquivo.' };
  const ncmPdf = require('./ncm_pdf');
  const hoje = new Date().toLocaleDateString('pt-BR');
  let logo = '';
  try { logo = 'data:image/png;base64,' + fs.readFileSync(logoPath()).toString('base64'); } catch (_) {}
  const nome = String((ncm.empresa || {}).nome || 'cliente').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);
  const per = ncmPdf.periodo(ncm.empresa || {}).replace(/\//g, '-').replace(/ a /g, ' a ');
  const save = await dialog.showSaveDialog(mainWindow, { title: 'Salvar PDF para o cliente', defaultPath: `Ajuste de NCM - ${nome}${per ? ' - ' + per : ''}.pdf`, filters: [{ name: 'PDF', extensions: ['pdf'] }] });
  if (save.canceled || !save.filePath) return { canceled: true };
  const htmlOut = path.join(os.tmpdir(), `fc_ncm_${Date.now()}.html`);
  const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, sandbox: true } });
  try {
    fs.writeFileSync(htmlOut, ncmPdf.html(ncm, logo, hoje), 'utf-8');
    await worker.loadFile(htmlOut);
    await new Promise((r) => setTimeout(r, 300));
    const pdf = await worker.webContents.printToPDF({ printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>', footerTemplate: ncmPdf.rodape(hoje) });
    fs.writeFileSync(save.filePath, pdf);
    shell.openPath(save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally { worker.destroy(); fs.unlink(htmlOut, () => {}); }
});
// Unidade × XML (só Admin): o código da unidade do C170 ("1") vira a unidade da nota ("UN") — inconsistência do portal, aba Estoque
ipcMain.handle('admin:unidAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath || !xmls) return { error: 'Selecione o SPED e os XMLs das notas.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_unid_${Date.now()}.json`);
  try {
    await runFiscal(['unidade-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:unidAplicar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath || !xmls) return { error: 'Selecione o SPED e os XMLs das notas.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_unid_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_unid_sped_${stamp}.txt`);
  try {
    await runFiscal(['unidade-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut, '--aplicar', '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
// Combustível/lubrificante como uso e consumo (só Admin): CFOP x.556/x.407 → x.653 no C170 e no C190
ipcMain.handle('admin:combAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_comb_${Date.now()}.json`);
  try {
    await runFiscal(['combustivel-cfop', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:combAplicar', async (_evt, { spedPath, usarCorrigido, xmls, ids }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath || !Array.isArray(ids) || !ids.length) return { error: 'Marque os itens que devem mudar de CFOP.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const idsJson = path.join(os.tmpdir(), `fc_comb_ids_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_comb_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_comb_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(idsJson, JSON.stringify(ids));
    await runFiscal(['combustivel-cfop', '--sped', base.arq, ...(xmls ? ['--xmls', xmls] : []), '--json', jsonOut, '--aplicar', idsJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    for (const f of [jsonOut, idsJson]) fs.unlink(f, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:descAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath || !xmls) return { error: 'Selecione o SPED e os XMLs de entrada.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_desc_${Date.now()}.json`);
  try {
    await runFiscal(['desconto-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:descAplicar', async (_evt, { spedPath, usarCorrigido, xmls, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath || !xmls) return { error: 'Selecione o SPED e os XMLs de entrada.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_desc_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_desc_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_desc_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['desconto-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Cadastro de produtos (0200): tipo 00 (revenda) que só entrou como uso e consumo / ativo → 07 / 08, revisado pelo Admin — só Admin
ipcMain.handle('admin:cad0200Analisar', async (_evt, { spedPath, usarCorrigido }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_cad_${Date.now()}.json`);
  try {
    await runFiscal(['cad-0200', '--sped', base.arq, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:cad0200Aplicar', async (_evt, { spedPath, usarCorrigido, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_cad_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_cad_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_cad_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['cad-0200', '--sped', base.arq, '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Crédito presumido de maçã e pera de outra UF (RICMS/RO, Anexo IV, Parte 2, item 19: C195 + C197 RO10000038) — só Admin
ipcMain.handle('admin:macaAnalisar', async (_evt, { spedPath, usarCorrigido }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_maca_${Date.now()}.json`);
  try {
    await runFiscal(['credito-maca', '--sped', base.arq, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:macaAplicar', async (_evt, { spedPath, usarCorrigido, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_maca_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_maca_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_maca_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['credito-maca', '--sped', base.arq, '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Crédito de fornecedor do Simples Nacional (RO: C195 + C197 RO00000001, campo 07 do E110) — só Admin
ipcMain.handle('admin:simplesAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  if (!xmls) return { error: 'Selecione os XMLs de entrada (.zip).' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_simples_${Date.now()}.json`);
  try {
    await runFiscal(['simples-ro', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:simplesAplicar', async (_evt, { spedPath, usarCorrigido, xmls, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_simples_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_simples_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_simples_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['simples-ro', '--sped', base.arq, '--xmls', xmls || '', '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ICMS creditado no SPED × ICMS destacado no XML da entrada (icms_xml.py) — só Admin
ipcMain.handle('admin:icmsXmlAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  if (!xmls) return { error: 'Selecione os XMLs de entrada (pasta ou .zip).' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_icmsxml_${Date.now()}.json`);
  try {
    await runFiscal(['icms-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:icmsXmlAplicar', async (_evt, { spedPath, usarCorrigido, xmls, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_icmsxml_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_icmsxml_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_icmsxml_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['icms-xml', '--sped', base.arq, '--xmls', xmls || '', '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
// Estoque de mercadoria que saiu da ST: crédito (Anexo VI, arts. 46 a 48) + inventário H005/H010/H020
ipcMain.handle('admin:estoqueStPlanilha', async () => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Planilha do estoque (código, descrição, quantidade, valor unitário)',
    filters: [{ name: 'Planilha', extensions: ['xlsx', 'csv'] }], properties: ['openFile'] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
async function _estoqueSt({ spedPath, usarCorrigido, planilha, xmls, params }, aplicar) {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  if (!planilha) return { error: 'Selecione a planilha do estoque.' };
  if (!xmls) return { error: 'Selecione os XMLs das notas de entrada.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const pj = path.join(os.tmpdir(), `fc_est_par_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_est_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_est_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(pj, JSON.stringify(params || {}), 'utf-8');
    await runFiscal(['estoque-st', '--sped', base.arq, '--planilha', planilha, '--xmls', xmls, '--params', pj, '--json', jsonOut,
      ...(aplicar ? ['--aplicar', '--saida', saida] : [])], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(pj, () => {});
    if (res.erro) return { error: res.erro };
    if (aplicar) {
      if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
      if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
      else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
      lastSpedCorrigidoPath = saida;
    }
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
}
ipcMain.handle('admin:estoqueStCalcular', (_evt, p) => _estoqueSt(p || {}, false));
ipcMain.handle('admin:estoqueStAplicar', (_evt, p) => _estoqueSt(p || {}, true));

// Valor do documento e base do ICMS × XML (entradas com crédito)
ipcMain.handle('admin:valorXmlAnalisar', async (_evt, { spedPath, usarCorrigido, xmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  if (!xmls) return { error: 'Selecione os XMLs de entrada (pasta ou .zip).' };
  const base = _difalBase(spedPath, usarCorrigido);
  const jsonOut = path.join(os.tmpdir(), `fc_valorxml_${Date.now()}.json`);
  try {
    await runFiscal(['valor-xml', '--sped', base.arq, '--xmls', xmls, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:valorXmlAplicar', async (_evt, { spedPath, usarCorrigido, xmls, selecao }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const base = _difalBase(spedPath, usarCorrigido);
  const stamp = Date.now();
  const selJson = path.join(os.tmpdir(), `fc_valorxml_sel_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_valorxml_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_valorxml_sped_${stamp}.txt`);
  try {
    fs.writeFileSync(selJson, JSON.stringify(selecao || {}), 'utf-8');
    await runFiscal(['valor-xml', '--sped', base.arq, '--xmls', xmls || '', '--json', jsonOut, '--aplicar', selJson, '--saida', saida], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(selJson, () => {});
    if (res.erro) return { error: res.erro };
    if (!fs.existsSync(saida)) return { error: 'O arquivo corrigido não foi gerado.' };
    if (lastSpedCorrigidoPath && lastSpedCorrigidoPath !== base.arq) fs.unlink(lastSpedCorrigidoPath, () => {});
    else if (lastSpedCorrigidoPath === base.arq && base.origem === 'corrigido') fs.unlink(base.arq, () => {});
    lastSpedCorrigidoPath = saida;
    return { ok: true, resumo: res, origem: base.origem };
  } catch (e) { return { error: String(e.message || e) }; }
});

let lastCorretorDash = null;   // dashboard da última correção (mostrado de imediato, sem rodar de novo)
ipcMain.handle('fiscal:corrigirSpedDashboard', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  if (lastCorretorDash && lastCorretorDash.spedPath === spedPath && lastCorretorDash.html) return { ok: true, html: lastCorretorDash.html };
  const htmlTmp = path.join(os.tmpdir(), `fc_corr_dash_${Date.now()}.html`);
  try {
    await runFiscal(['corrigir', spedPath, '--saida', path.join(os.tmpdir(), `fc_corr_dash_sped_${Date.now()}.txt`), '--html', htmlTmp], htmlTmp);
    const html = fs.readFileSync(htmlTmp, 'utf-8');
    fs.unlink(htmlTmp, () => {});
    return { ok: true, html };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:substituirLmc', async (_evt, { semLmcPath, comLmcPath }) => {
  if (!semLmcPath || !comLmcPath) return { error: 'Selecione os 2 arquivos.' };
  const saidaTmp = path.join(os.tmpdir(), `fc_lmc_${Date.now()}.txt`);
  const resumoTmp = path.join(os.tmpdir(), `fc_lmc_resumo_${Date.now()}.json`);
  try {
    await runFiscal(['substituir-lmc', semLmcPath, '--com-lmc', comLmcPath, '--saida', saidaTmp, '--json', resumoTmp], saidaTmp);
    const resumo = JSON.parse(fs.readFileSync(resumoTmp, 'utf-8'));
    fs.unlink(resumoTmp, () => {});
    if (resumo.erro) { fs.unlink(saidaTmp, () => {}); return { error: resumo.erro }; }
    if (lastSpedLmcPath) fs.unlink(lastSpedLmcPath, () => {});
    lastSpedLmcPath = saidaTmp;
    return { ok: true, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:lmcDashboard', async (_evt, { semLmcPath, comLmcPath }) => {
  if (!semLmcPath || !comLmcPath) return { error: 'Selecione os 2 arquivos.' };
  const htmlTmp = path.join(os.tmpdir(), `fc_lmc_dash_${Date.now()}.html`);
  try {
    await runFiscal(['substituir-lmc', semLmcPath, '--com-lmc', comLmcPath, '--saida', path.join(os.tmpdir(), `fc_lmc_dash_sped_${Date.now()}.txt`), '--html', htmlTmp], htmlTmp);
    const html = fs.readFileSync(htmlTmp, 'utf-8');
    fs.unlink(htmlTmp, () => {});
    return { ok: true, html };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:baixarSpedLmc', async () => {
  if (!lastSpedLmcPath || !fs.existsSync(lastSpedLmcPath)) return { error: 'Rode a substituição primeiro.' };
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar SPED com LMC substituído', defaultPath: 'sped_com_lmc_corrigido.txt',
    filters: [{ name: 'SPED', extensions: ['txt'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  try {
    fs.copyFileSync(lastSpedLmcPath, save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:visualizarSpedCorrigido', async () => {
  if (!lastSpedCorrigidoPath || !fs.existsSync(lastSpedCorrigidoPath)) {
    return { error: 'Rode a correção primeiro.' };
  }
  const htmlOut = path.join(os.tmpdir(), `fc_viz_corr_${Date.now()}.html`);
  try {
    await runFiscal(['visualizar-sped', lastSpedCorrigidoPath, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
    return { ok: true, html };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:baixarSpedCorrigido', async () => {
  if (!lastSpedCorrigidoPath || !fs.existsSync(lastSpedCorrigidoPath)) {
    return { error: 'Nenhum SPED corrigido disponível ainda. Rode a correção primeiro.' };
  }
  const r = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar SPED Fiscal corrigido',
    defaultPath: 'SPED_Fiscal_corrigido.txt',
    filters: [{ name: 'Texto', extensions: ['txt'] }],
  });
  if (r.canceled || !r.filePath) return { canceled: true };
  fs.copyFileSync(lastSpedCorrigidoPath, r.filePath);
  return { ok: true, path: r.filePath };
});

ipcMain.handle('fiscal:pickXmlsFolder', async () => {
  // Só .zip a partir da v1.3.2 — pasta solta e .xml avulso tirados de
  // propósito (pedido dele): antivírus do Windows escaneando milhares de
  // XML solto era o gargalo real, e o .zip já cobre tudo isso sozinho.
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione um ou mais arquivos .zip com as notas',
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'ZIP', extensions: ['zip'] }],
  });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths.join(path.delimiter) };
});

ipcMain.handle('fiscal:pickPgdas', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione o Extrato do PGDAS-D (PDF)',
    properties: ['openFile'],
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return { path: r.filePaths[0] };
});

ipcMain.handle('fiscal:pickEfdContrib', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione o arquivo da EFD-Contribuições (.txt)',
    properties: ['openFile'],
    filters: [{ name: 'EFD-Contribuições', extensions: ['txt'] }],
  });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return { path: r.filePaths[0] };
});

ipcMain.handle('fiscal:pickDominioPdf', async (_evt, rotulo) => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: `Selecione o Acompanhamento de ${rotulo || 'Entradas/Saídas'} do Domínio (PDF)`,
    properties: ['openFile'],
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return { path: r.filePaths[0] };
});

ipcMain.handle('fiscal:efdContrib', async (_evt, arquivoPath, opcoes = {}) => {
  if (!arquivoPath) return { error: 'Selecione o arquivo da EFD-Contribuições.' };
  const htmlOut = path.join(os.tmpdir(), `fc_efd_painel_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_efd_resumo_${Date.now()}.json`);
  try {
    const args = ['efd-contribuicoes', arquivoPath, '--painel-html', htmlOut, '--json', jsonOut];
    if (opcoes && opcoes.entradas) args.push('--dominio-entradas', opcoes.entradas);
    if (opcoes && opcoes.saidas) args.push('--dominio-saidas', opcoes.saidas);
    await runFiscal(args, jsonOut);
    const resumo = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    if (resumo.erro) return { error: resumo.erro };
    const painelHtml = fs.readFileSync(htmlOut, 'utf-8');
    [htmlOut, jsonOut].forEach((p) => fs.unlink(p, () => {}));
    return { ok: true, resumo, painelHtml };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ---- Relatório para o CLIENTE (EFD-Contribuições): explicação automática + dashboards ----
ipcMain.handle('fiscal:efdCliente', async (_evt, { spedPath, anteriorPath, opcoes }) => {
  if (!spedPath) return { error: 'Abra primeiro o arquivo da EFD-Contribuições.' };
  const stamp = Date.now();
  const f = (ext) => path.join(os.tmpdir(), `fc_efdcli_${stamp}.${ext}`);
  const htmlOut = f('html'), estOut = f('est.html'), jsonOut = f('json'), optJson = f('opts.json');
  try {
    fs.writeFileSync(optJson, JSON.stringify(opcoes || {}), 'utf-8');
    const args = ['efd-cliente', spedPath, '--html', htmlOut, '--html-estatico', estOut, '--json', jsonOut, '--opcoes', optJson];
    if (anteriorPath) args.push('--anterior', anteriorPath);
    await runFiscal(args, jsonOut);
    const meta = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    if (meta.erro) return { error: meta.erro };
    const html = fs.readFileSync(htmlOut, 'utf-8');
    const htmlEstatico = fs.readFileSync(estOut, 'utf-8');
    [htmlOut, estOut, jsonOut, optJson].forEach((p) => fs.unlink(p, () => {}));
    return { ok: true, html, htmlEstatico, resumo: meta.resumo, avisos: meta.avisos || [] };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:efdClienteSalvar', async (_evt, { html, nomeSugerido }) => {
  const nome = nfseLote.sanitizar(nomeSugerido || 'Relatorio-Cliente');
  const r = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar relatório do cliente (HTML)', defaultPath: `${nome}.html`, filters: [{ name: 'HTML', extensions: ['html'] }],
  });
  if (r.canceled || !r.filePath) return { canceled: true };
  try { fs.writeFileSync(r.filePath, html, 'utf-8'); return { ok: true, path: r.filePath }; }
  catch (e) { return { error: String(e.message || e) }; }
});

// PDF: usa a versão ESTÁTICA do relatório (sem animação), então o PDF sai sempre no estado final
ipcMain.handle('fiscal:efdClientePdf', async (_evt, { htmlEstatico, nomeSugerido }) => {
  const nome = nfseLote.sanitizar(nomeSugerido || 'Relatorio-Cliente');
  const r = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar relatório do cliente (PDF)', defaultPath: `${nome}.pdf`, filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (r.canceled || !r.filePath) return { canceled: true };
  const tmp = path.join(os.tmpdir(), `fc_cli_pdf_${Date.now()}.html`);
  fs.writeFileSync(tmp, htmlEstatico, 'utf-8');
  const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true } });
  try {
    await win.loadFile(tmp);
    await new Promise((ok) => setTimeout(ok, 400));
    const pdf = await win.webContents.printToPDF({ printBackground: true, preferCSSPageSize: true });
    fs.writeFileSync(r.filePath, pdf);
    return { ok: true, path: r.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { try { win.destroy(); } catch (_) {} fs.unlink(tmp, () => {}); }
});

ipcMain.handle('fiscal:pickPvaPdf', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'Selecione o relatório de erros do PVA (PDF)',
    properties: ['openFile'],
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (r.canceled || !r.filePaths[0]) return { canceled: true };
  return { path: r.filePaths[0] };
});

// 2.4.56: XMLs das NF-e de saída (vários arquivos .xml e/ou .zip) para montar os itens das notas que vieram sem C170
ipcMain.handle('fiscal:pickXmlsSaida', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: 'XMLs das NF-e de saída (pode escolher vários ou o .zip)',
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'XML ou ZIP', extensions: ['xml', 'zip'] }],
  });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
});

ipcMain.handle('fiscal:efdCorrigir', async (_evt, spedPath, pvaPath, contaAjuste, contaUso, contaEntrada, itensSem, incluir0500, incluir0900, xmls) => {
  if (!spedPath) return { error: 'Selecione o arquivo da EFD-Contribuições.' };
  const stamp = Date.now();
  const htmlOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.json`);
  const txtOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.txt`);
  try {
    const args = ['efd-corrigir', spedPath, '--saida', txtOut, '--painel-html', htmlOut, '--json', jsonOut];
    if (pvaPath) args.push('--pva', pvaPath);
    if (contaAjuste && /^[\w.\-]{1,60}$/.test(String(contaAjuste).trim())) args.push('--conta-ajuste', String(contaAjuste).trim());
    const okConta = (c) => /^[\w.\-]{1,60}$/.test(String(c || '').trim());
    args.push('--conta-uso', okConta(contaUso) ? String(contaUso).trim() : '', '--conta-entrada', okConta(contaEntrada) ? String(contaEntrada).trim() : '');
    if (itensSem) args.push('--itens-genericos');
    if (incluir0500) args.push('--incluir-0500');
    if (incluir0900) args.push('--incluir-0900');
    const xmlLista = path.join(os.tmpdir(), `fc_efdcorr_${stamp}_xmls.json`);
    const listaXml = (Array.isArray(xmls) ? xmls : []).filter((x) => typeof x === 'string' && fs.existsSync(x));
    if (listaXml.length) { fs.writeFileSync(xmlLista, JSON.stringify(listaXml), 'utf-8'); args.push('--xml-lista', xmlLista); }
    await runFiscal(args, jsonOut);
    fs.unlink(xmlLista, () => {});
    const resumo = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    if (resumo.erro) return { error: resumo.erro };
    const painelHtml = fs.readFileSync(htmlOut, 'utf-8');
    [htmlOut, jsonOut].forEach((p) => fs.unlink(p, () => {}));
    return { ok: true, resumo, painelHtml, corrigidoPath: txtOut };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ⚡ Corrigir monofásico (Admin · Correção da EFD-Contribuições) — trabalha em cima do arquivo já
// corrigido na sessão, se houver (efdPath vem do renderer: corrigido ou original).
ipcMain.handle('admin:monoAnalisar', async (_evt, { efdPath }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!efdPath || !fs.existsSync(efdPath)) return { error: 'Selecione o arquivo da EFD-Contribuições.' };
  const jsonOut = path.join(os.tmpdir(), `fc_mono_${Date.now()}.json`);
  try {
    await runFiscal(['monofasico', 'analisar', efdPath, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:monoAplicar', async (_evt, { efdPath, grupos }) => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  if (!efdPath || !fs.existsSync(efdPath)) return { error: 'Selecione o arquivo da EFD-Contribuições.' };
  const stamp = Date.now();
  const jsonOut = path.join(os.tmpdir(), `fc_mono_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_mono_efd_${stamp}.txt`);
  try {
    await runFiscal(['monofasico', 'aplicar', efdPath, '--grupos', JSON.stringify(grupos || []), '--saida', saida, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res, corrigidoPath: saida };
  } catch (e) { return { error: String(e.message || e) }; }
});

// ⚡ Automatizar correção — SPED Fiscal de todos os clientes do mês (lote_sped.py; só Admin)
let loteSaidaDir = null;
ipcMain.handle('admin:lotePickPasta', async (_evt, { titulo } = {}) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  let inicial;
  try { inicial = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!inicial && fs.existsSync(PASTA_PADRAO_NFSE)) inicial = PASTA_PADRAO_NFSE;
  const r = await dialog.showOpenDialog(mainWindow, {
    title: titulo || 'Escolha a pasta do mês (MM-AAAA) com os SPED Fiscais dos clientes', defaultPath: inicial,
    properties: ['openDirectory'],
  });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { path: r.filePaths[0] };
});
ipcMain.handle('admin:loteAnalisar', async (_evt, { pasta, pastaXmls }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!pasta || !fs.existsSync(pasta)) return { error: 'Escolha a pasta do mês.' };
  const jsonOut = path.join(os.tmpdir(), `fc_lote_an_${Date.now()}.json`);
  try {
    const regimes = await _regimesJson(_spedsDaPasta(pasta));
    await runFiscal(['lote-sped', 'analisar', '--pasta', pasta, ...(pastaXmls ? ['--pasta-xmls', pastaXmls] : []), '--regimes', regimes, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(regimes, () => {});
    if (res.erro) return { error: res.erro };
    return { ok: true, res };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:loteAplicar', async (_evt, { plano }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  const stamp = Date.now();
  const planoJson = path.join(os.tmpdir(), `fc_lote_plano_${stamp}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_lote_res_${stamp}.json`);
  const saida = path.join(os.tmpdir(), `fc_lote_${stamp}`);
  try {
    fs.writeFileSync(planoJson, JSON.stringify(plano || {}), 'utf-8');
    const regimes = await _regimesJson(((plano && plano.arquivos) || []).map((a) => a.sped).filter(Boolean));
    await runFiscal(['lote-sped', 'aplicar', '--plano', planoJson, '--saida', saida, '--regimes', regimes, '--json', jsonOut], jsonOut);
    const res = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {}); fs.unlink(planoJson, () => {}); fs.unlink(regimes, () => {});
    if (res.erro) return { error: res.erro };
    if (loteSaidaDir && loteSaidaDir !== saida) fs.rm(loteSaidaDir, { recursive: true, force: true }, () => {});
    loteSaidaDir = saida;
    return { ok: true, res };
  } catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('admin:loteSalvar', async (_evt, { arquivo }) => {
  const bloq = _soAdminCorretor(); if (bloq) return bloq;
  if (!arquivo || !fs.existsSync(arquivo) || !loteSaidaDir || !path.resolve(arquivo).startsWith(path.resolve(loteSaidaDir))) {
    return { error: 'Arquivo não encontrado. Rode a correção automática de novo.' };
  }
  const zip = /\.zip$/i.test(arquivo);
  const save = await dialog.showSaveDialog(mainWindow, {
    title: zip ? 'Salvar todos os SPEDs corrigidos (.zip)' : 'Salvar SPED Fiscal corrigido', defaultPath: path.basename(arquivo),
    filters: [zip ? { name: 'ZIP', extensions: ['zip'] } : { name: 'Texto', extensions: ['txt'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  try { fs.copyFileSync(arquivo, save.filePath); return { ok: true, path: save.filePath }; } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:efdCorrigirSalvar', async (_evt, corrigidoPath, nomeOriginal) => {
  if (!corrigidoPath || !fs.existsSync(corrigidoPath)) return { error: 'Arquivo corrigido não encontrado. Rode a correção de novo.' };
  const base = String(nomeOriginal || 'sped.txt').replace(/\.txt$/i, '');
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar EFD-Contribuições corrigida', defaultPath: `${base}_corrigido.txt`,
    filters: [{ name: 'EFD-Contribuições', extensions: ['txt'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  try {
    fs.copyFileSync(corrigidoPath, save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

// App do celular: os números do mês de cada SPED analisado (só totais, como no BI) em sped_totais/{cnpj}_{AAAA-MM}
function _spedTotaisNuvem(arq) {
  setTimeout(async () => {
    try {
      const t = JSON.parse(fs.readFileSync(arq, 'utf-8')); fs.unlink(arq, () => {});
      const db = auth.db(), f = auth.fsMod();
      if (!db || !f || !/^\d{14}$/.test(t.cnpj) || !/^\d{4}-\d{2}$/.test(t.comp)) return;
      const ses = auth.sessao() || {};
      await f.setDoc(f.doc(db, 'sped_totais', `${t.cnpj}_${t.comp}`), { ...t, em: new Date().toISOString(), por: ses.nome || ses.email || '' });
    } catch (_) { /* sem internet ou sem o arquivo: o celular só não mostra este mês */ }
  }, 300);
}

ipcMain.handle('fiscal:dashboard', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const htmlOut = path.join(os.tmpdir(), `fc_sped_${Date.now()}.html`);
  const totOut = htmlOut.replace(/\.html$/, '_tot.json');
  try {
    await runFiscal(['sped', spedPath, '--dashboard-html', htmlOut, '--totais-json', totOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
    _spedTotaisNuvem(totOut);
    let empresa = '';
    const m = html.match(/<h1>([^<]+)<\/h1>/); if (m) empresa = m[1];
    return { ok: true, html, empresa };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:documentos', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const htmlOut = path.join(os.tmpdir(), `fc_docs_${Date.now()}.html`);
  try {
    await runFiscal(['sped', spedPath, '--documentos-html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
    let empresa = '';
    const m = html.match(/<h1>([^<]+)<\/h1>/); if (m) empresa = m[1];
    return { ok: true, html, empresa };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:conferencia', async (_evt, { spedPath, xmlsPath }) => {
  if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e a pasta de XMLs.' };
  const htmlOut = path.join(os.tmpdir(), `fc_conf_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_conf_${Date.now()}.json`);
  try {
    await runFiscal(['conferencia', spedPath, '--xmls', xmlsPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { importadas: j.importadas, conciliadas: j.qtd_conciliadas, faltantes: j.qtd_faltantes, divergencias: j.qtd_divergencias };
      empresaConf = (j.empresa && j.empresa.empresa) || '';
    } catch (_) {}
    if (lastConfJson && lastConfJson !== jsonOut) fs.unlink(lastConfJson, () => {});
    lastConfJson = fs.existsSync(jsonOut) ? jsonOut : null;     // guardado para o "Exportar Excel"
    fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

// Conferência NF-e × SPED em Excel (para o cliente): abas "Faltantes no SPED" e "Divergência de valor"
let lastConfJson = null; let empresaConf = '';
ipcMain.handle('fiscal:confExportarXlsx', async () => {
  if (!lastConfJson || !fs.existsSync(lastConfJson)) return { error: 'Rode a conferência primeiro.' };
  const nome = `Conferencia-Entradas-SPED-x-XML-${(empresaConf || 'empresa').replace(/[^\w-]+/g, '_')}.xlsx`;
  const save = await dialog.showSaveDialog(mainWindow, { title: 'Salvar Excel', defaultPath: nome, filters: [{ name: 'Excel', extensions: ['xlsx'] }] });
  if (save.canceled || !save.filePath) return { canceled: true };
  const jsonRes = path.join(os.tmpdir(), `fc_confx_${Date.now()}.json`);
  try {
    await runFiscal(['conf-xlsx', '--entrada', lastConfJson, '--saida', save.filePath, '--json', jsonRes], jsonRes);
    const r = JSON.parse(fs.readFileSync(jsonRes, 'utf-8')); fs.unlink(jsonRes, () => {});
    if (r.erro) return { error: r.erro };
    shell.openPath(save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:conferenciaSaidas', async (_evt, { spedPath, xmlsPath }) => {
  if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e a pasta de XMLs.' };
  const htmlOut = path.join(os.tmpdir(), `fc_confs_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_confs_${Date.now()}.json`);
  try {
    await runFiscal(['conferencia-saidas', spedPath, '--xmls', xmlsPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { importadas: j.importadas, conciliadas: j.qtd_conciliadas, faltantes: j.qtd_faltantes, divergencias: j.qtd_divergencias };
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:prepararInclusao', async (_evt, { spedPath, xmlsPath }) => {
  if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e a pasta de XMLs.' };
  const jsonOut = path.join(os.tmpdir(), `fc_prep_${Date.now()}.json`);
  try {
    await runFiscal(['preparar-inclusao', spedPath, '--xmls', xmlsPath, '--json', jsonOut], jsonOut);
    const dados = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    return { ok: true, ...dados };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:incluirNotas', async (_evt, { spedPath, notas, sugestao }) => {
  if (!spedPath || !notas || !notas.length) return { error: 'Nenhuma nota selecionada.' };
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar SPED com as notas incluídas',
    defaultPath: (sugestao || 'sped-com-notas') + '.txt',
    filters: [{ name: 'TXT', extensions: ['txt'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  const entradaPath = path.join(os.tmpdir(), `fc_entrada_incluir_${Date.now()}.json`);
  const jsonOut = path.join(os.tmpdir(), `fc_resumo_incluir_${Date.now()}.json`);
  try {
    fs.writeFileSync(entradaPath, JSON.stringify(notas));
    await runFiscal(['incluir-notas', spedPath, '--entrada', entradaPath, '--saida', save.filePath, '--json', jsonOut], save.filePath);
    let resumo = {};
    try { resumo = JSON.parse(fs.readFileSync(jsonOut, 'utf-8')); } catch (_) {}
    return { ok: true, path: save.filePath, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
  finally { fs.unlink(entradaPath, () => {}); fs.unlink(jsonOut, () => {}); }
});

ipcMain.handle('fiscal:desoneracao', async (_evt, { xmlsPath }) => {
  if (!xmlsPath) return { error: 'Selecione a pasta de XMLs.' };
  const htmlOut = path.join(os.tmpdir(), `fc_deson_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_deson_${Date.now()}.json`);
  try {
    await runFiscal(['desoneracao', '--xmls', xmlsPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { identificado: j.identificado, comDeson: j.qtd_com_deson, totalDeson: j.total_deson };
      _biRegistrar('deson', j);
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:listarNotasXml', async (_evt, xmlsPath) => {
  if (!xmlsPath) return { error: 'Selecione o .zip dos XMLs.' };
  const jsonOut = path.join(os.tmpdir(), `fc_notas_${Date.now()}.json`);
  try {
    await runFiscal(['listar-notas-xml', xmlsPath, '--json', jsonOut], jsonOut);
    const notas = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    fs.unlink(jsonOut, () => {});
    return { ok: true, notas };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:gerarDanfe', async (_evt, { xmlsPath, chave }) => {
  if (!xmlsPath || !chave) return { error: 'Falta o .zip dos XMLs ou a chave da nota.' };
  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar DANFE', defaultPath: `DANFE_${chave}.pdf`,
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (save.canceled || !save.filePath) return { canceled: true };
  try {
    await runFiscal(['danfe', xmlsPath, '--chave', chave, '--saida', save.filePath], save.filePath);
    return { ok: true, path: save.filePath };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:icmsCredito', async (_evt, { spedPath, xmlsPath }) => {
  if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e o .zip dos XMLs de entrada.' };
  const htmlOut = path.join(os.tmpdir(), `fc_icmscred_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_icmscred_${Date.now()}.json`);
  try {
    await runFiscal(['icms-credito', spedPath, '--xmls', xmlsPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { divergentes: j.qtd_divergentes, corretas: j.qtd_corretas, ignoradas: j.qtd_ignoradas, totalDivergencia: j.total_divergencia };
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:frete', async (_evt, { spedPath, xmlsPath }) => {
  if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e a pasta de XMLs de CT-e.' };
  const htmlOut = path.join(os.tmpdir(), `fc_frete_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_frete_${Date.now()}.json`);
  try {
    await runFiscal(['frete', spedPath, '--xmls', xmlsPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { qtdCtes: j.qtd_ctes, custo: j.qtd_custo, despesa: j.qtd_despesa, naoCte: j.nao_cte };
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:classificacao', async (_evt, { spedPath }) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const htmlOut = path.join(os.tmpdir(), `fc_classif_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_classif_${Date.now()}.json`);
  try {
    await runFiscal(['classificacao', spedPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = { cfopCst: j.qtd_cfop_cst, mesmoItem: j.qtd_mesmo_item, combustivel: j.qtd_combustivel, remessaRetorno: j.qtd_remessa_retorno };
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

let lastPgdasPath = null;
ipcMain.handle('fiscal:pgdas', async (_evt, pdfPath) => {
  if (!pdfPath) return { error: 'Selecione o Extrato do PGDAS-D.' };
  const htmlOut = path.join(os.tmpdir(), `fc_pgdas_${Date.now()}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_pgdas_${Date.now()}.json`);
  try {
    await runFiscal(['pgdas', pdfPath, '--json', jsonOut, '--html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    let resumo = {};
    try {
      const j = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
      resumo = {
        empresa: j.contribuinte && j.contribuinte.nome_empresarial,
        pa: j.apuracao && j.apuracao.pa,
        aliquota: j.aliquota_oficial && j.aliquota_oficial.aliquota_efetiva,
        dasTotal: j.das && j.das.total,
      };
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    lastPgdasPath = pdfPath;
    return { ok: true, html, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:export', async (_evt, { fmt, payload }) => {
  const { kind, spedPath, xmlsPath, pgdasPath, cliente, comLmcPath } = payload || {};
  if (kind === 'desoneracao') { if (!xmlsPath) return { error: 'Importe os XMLs antes de exportar.' }; }
  else if (kind === 'pgdas') { if (!pgdasPath) return { error: 'Importe o Extrato do PGDAS-D antes de exportar.' }; }
  else if (kind === 'lmc') { if (!spedPath || !comLmcPath) return { error: 'Selecione os 2 arquivos antes de exportar.' }; }
  else if (kind === 'icmsCredito') { if (!spedPath || !xmlsPath) return { error: 'Selecione o SPED e o .zip dos XMLs antes de exportar.' }; }
  else if (!spedPath) return { error: 'Importe os dados antes de exportar.' };
  const base = (kind === 'dashboard' ? 'Dashboard-SPED'
    : kind === 'documentos' ? 'Documentos-Entrada'
    : kind === 'confSaidas' ? 'Conferencia-Saidas-SPED'
    : kind === 'desoneracao' ? 'Conferencia-ICMS-Desonerado'
    : kind === 'frete' ? 'Classificacao-Frete-CTe'
    : kind === 'classificacao' ? 'Auditor-Classificacao-Fiscal'
    : kind === 'pgdas' ? 'Painel-Simples-Nacional'
    : kind === 'corretor' ? 'Corretor-SPED-Fiscal'
    : kind === 'lmc' ? 'Substituicao-LMC'
    : kind === 'icmsCredito' ? 'Conferencia-ICMS-Credito'
    : 'Conferencia-NFe-SPED') + (cliente ? '-Cliente' : '');
  const clienteArgs = cliente ? ['--cliente'] : [];
  const htmlTmp = path.join(os.tmpdir(), `fc_exp_${Date.now()}.html`);
  try {
    if (kind === 'dashboard') await runFiscal(['sped', spedPath, '--dashboard-html', htmlTmp], htmlTmp);
    else if (kind === 'documentos') await runFiscal(['sped', spedPath, '--documentos-html', htmlTmp], htmlTmp);
    else if (kind === 'confSaidas') await runFiscal(['conferencia-saidas', spedPath, '--xmls', xmlsPath, '--html', htmlTmp, ...clienteArgs], htmlTmp);
    else if (kind === 'desoneracao') await runFiscal(['desoneracao', '--xmls', xmlsPath, '--html', htmlTmp], htmlTmp);
    else if (kind === 'frete') await runFiscal(['frete', spedPath, '--xmls', xmlsPath, '--html', htmlTmp], htmlTmp);
    else if (kind === 'classificacao') await runFiscal(['classificacao', spedPath, '--html', htmlTmp], htmlTmp);
    else if (kind === 'pgdas') await runFiscal(['pgdas', pgdasPath, '--html', htmlTmp], htmlTmp);
    else if (kind === 'corretor') await runFiscal(['corrigir', spedPath, '--saida', path.join(os.tmpdir(), `fc_corr_sped_${Date.now()}.txt`), '--html', htmlTmp], htmlTmp);
    else if (kind === 'lmc') await runFiscal(['substituir-lmc', spedPath, '--com-lmc', comLmcPath, '--saida', path.join(os.tmpdir(), `fc_lmc_sped_${Date.now()}.txt`), '--html', htmlTmp], htmlTmp);
    else if (kind === 'icmsCredito') await runFiscal(['icms-credito', spedPath, '--xmls', xmlsPath, '--html', htmlTmp], htmlTmp);
    else await runFiscal(['conferencia', spedPath, '--xmls', xmlsPath, '--html', htmlTmp, ...clienteArgs], htmlTmp);
  } catch (e) { return { error: String(e.message || e) }; }

  const save = await dialog.showSaveDialog(mainWindow, {
    title: 'Salvar ' + fmt.toUpperCase(),
    defaultPath: base + (fmt === 'pdf' ? '.pdf' : '.html'),
    filters: [{ name: fmt.toUpperCase(), extensions: [fmt] }],
  });
  if (save.canceled || !save.filePath) { fs.unlink(htmlTmp, () => {}); return { canceled: true }; }

  try {
    if (fmt === 'html') {
      fs.copyFileSync(htmlTmp, save.filePath);
    } else {
      const worker = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
      try {
        await worker.loadFile(htmlTmp);
        await new Promise((r) => setTimeout(r, 1600)); // deixa as animações concluírem
        const pdf = await worker.webContents.printToPDF({ printBackground: true, pageSize: 'A4', landscape: true, margins: { marginType: 'none' } });
        fs.writeFileSync(save.filePath, pdf);
      } finally { worker.destroy(); }
    }
    return { ok: true, path: save.filePath };
  } catch (e) {
    return { error: String(e.message || e) };
  } finally {
    fs.unlink(htmlTmp, () => {});
  }
});

ipcMain.handle('app:openPath', async (_evt, p) => {
  if (p) shell.showItemInFolder(p);
  return true;
});

// abre o arquivo no programa padrão (ex.: relatório HTML no navegador) — diferente de openPath, que só destaca na pasta
ipcMain.handle('app:abrirArquivo', async (_evt, p) => {
  if (!p) return { error: 'Caminho vazio.' };
  const r = await shell.openPath(p);
  return r ? { error: r } : { ok: true };
});

ipcMain.handle('app:version', async () => app.getVersion());

// ---- controles da janela (frameless) --------------------------------------
ipcMain.on('win:minimize', () => mainWindow && mainWindow.minimize());
ipcMain.on('win:maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('win:close', () => mainWindow && mainWindow.close());
ipcMain.handle('win:isMaximized', () => (mainWindow ? mainWindow.isMaximized() : false));
