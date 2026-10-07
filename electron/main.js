'use strict';
const { app, BrowserWindow, ipcMain, dialog, shell, safeStorage, net } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn } = require('child_process');
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
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 460,
    height: 320,
    frame: false,
    resizable: false,
    transparent: true,
    alwaysOnTop: true,
    center: true,
    show: true,
    webPreferences: { contextIsolation: true },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
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

  const started = Date.now();
  mainWindow.once('ready-to-show', () => {
    const wait = Math.max(0, 3500 - (Date.now() - started)); // splash mínimo (~3,5s)
    setTimeout(() => {
      if (splashWindow) { splashWindow.close(); splashWindow = null; }
      mainWindow.maximize(); // sempre abre em tela cheia (login incluso, é a mesma janela)
      mainWindow.show();
    }, wait);
  });

  mainWindow.on('closed', () => (mainWindow = null));
}

app.whenReady().then(() => {
  createSplash();
  createMainWindow();

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
// Canal de notícias contábeis (balão não intrusivo, some sozinho)
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
      let itens = permitidos.filter((i) => i.guid && !cfg.vistos.includes(i.guid));
      let reiniciou = false;
      // pedido do Rafael, 30/09: nunca fica "sem nada pra mostrar" — se já
      // passou por todas as notícias disponíveis, esquece o que já foi
      // visto e recomeça do início da lista atual (mantém sempre alguma
      // notícia circulando, em vez de ficar quieto esperando algo genuinamente novo).
      if (!itens.length && permitidos.length) {
        cfg.vistos = [];
        itens = permitidos;
        reiniciou = true;
      }
      _newsLog({ ok: true, codificacao, itensNoFeed: todos.length, itensNovos: itens.length, reiniciou });
      if (!itens.length) return;
      // só a mais nova de cada checagem — nunca empilha vários balões juntos
      const nova = itens[0];
      cfg.vistos = [nova.guid, ...cfg.vistos].slice(0, 300);
      _newsSalvarConfig(cfg);
      if (mainWindow) mainWindow.webContents.send('news:novo', nova);
    } catch (e) { _newsLog({ ok: false, motivo: 'Erro ao interpretar o feed: ' + String(e.message || e) }); }
  });
}

ipcMain.handle('news:status', () => (_newsLerConfig().desativado ? 'desativado' : 'ativo'));
ipcMain.handle('news:desativar', () => { const c = _newsLerConfig(); c.desativado = true; _newsSalvarConfig(c); return true; });
ipcMain.handle('news:ativar', () => { const c = _newsLerConfig(); c.desativado = false; _newsSalvarConfig(c); return true; });
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
// ---- Login por senha (controla acesso Fiscal / Contábil / Admin) ----
// As senhas ficam só aqui no processo principal, fora do alcance do renderer.
const AUTH_SENHAS = {
  'Liddera@1': 'fiscal',
  'Liddera@2': 'contabil',
  'Liddera@7092': 'admin',
};
let sessionRole = null; // papel da sessão atual (usado para travar os módulos exclusivos do Admin)
ipcMain.handle('auth:login', (_evt, senha) => {
  const role = AUTH_SENHAS[String(senha || '')];
  if (!role) return { ok: false };
  sessionRole = role;
  return { ok: true, role };
});

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

ipcMain.handle('fiscal:certSalvar', async (_evt, { pfxPath, senha, info }) => {
  try {
    // achado real (Rafael, 25/09/2026): certificado vencido não dá um erro
    // claro na hora de baixar — a Receita simplesmente rejeita a conexão
    // (aparece como falha de TLS, sem explicar o motivo real). Bloqueia
    // aqui, no cadastro, pra nem deixar salvar um certificado já vencido.
    if (info.validade && new Date(info.validade) < new Date()) {
      return { error: `Esse certificado está VENCIDO desde ${info.validade.split('-').reverse().join('/')} — não vai funcionar pra baixar nada. Peça um certificado válido antes de cadastrar.` };
    }
    const indice = _lerIndiceCert();
    const id = `${info.cnpj}_${Date.now()}`;
    const pfxDestino = path.join(_certDir(), `${id}.pfx`);
    fs.copyFileSync(pfxPath, pfxDestino);
    if (safeStorage.isEncryptionAvailable()) {
      const senhaCifrada = safeStorage.encryptString(senha);
      fs.writeFileSync(path.join(_certDir(), `${id}.senha`), senhaCifrada);
    } else {
      return { error: 'A criptografia segura do sistema operacional não está disponível nesta máquina — não vou salvar a senha sem ela.' };
    }
    indice.empresas = indice.empresas.filter((e) => e.cnpj !== info.cnpj); // recadastro substitui o antigo
    indice.empresas.push({
      id, cnpj: info.cnpj, razaoSocial: info.razao_social, validade: info.validade,
      pfxArquivo: `${id}.pfx`, ultimoNsu: 0, ultimoDownload: null,
    });
    _salvarIndiceCert(indice);
    return { ok: true };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:certListar', () => {
  const indice = _lerIndiceCert();
  return indice.empresas.map((e) => ({
    id: e.id, cnpj: e.cnpj, razaoSocial: e.razaoSocial, validade: e.validade,
    ultimoDownload: e.ultimoDownload,
  }));
});

ipcMain.handle('fiscal:certRemover', (_evt, id) => {
  try {
    const indice = _lerIndiceCert();
    const alvo = indice.empresas.find((e) => e.id === id);
    if (!alvo) return { error: 'Empresa não encontrada.' };
    for (const arq of [alvo.pfxArquivo, `${id}.senha`]) {
      const p = path.join(_certDir(), arq);
      if (fs.existsSync(p)) fs.unlinkSync(p);
    }
    indice.empresas = indice.empresas.filter((e) => e.id !== id);
    _salvarIndiceCert(indice);
    return { ok: true };
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

async function _analisarNfseEmpresa(empresa, dataInicial, dataFinal, opcoes = {}) {
  if (!dataInicial || !dataFinal) return { error: 'Informe a Data inicial e a Data final para ver o painel.' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde os documentos são salvos primeiro.' };
  const pastaEmpresa = path.join(pastaBase, empresa.razaoSocial);
  if (!fs.existsSync(pastaEmpresa)) {
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
      '--painel-html', painelTmp, '--json', jsonTmp];
    if (dataInicial) args.push('--inicio', dataInicial);
    if (dataFinal) args.push('--fim', dataFinal);
    await runFiscal(args, jsonTmp);
    const resumo = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    const painelHtml = fs.readFileSync(painelTmp, 'utf-8');
    [painelTmp, jsonTmp].forEach((p) => fs.unlink(p, () => {}));
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
  const nomeArquivo = { 'efd-contrib': 'Conferencia-EFD-Contribuicoes', 'efd-corrigir': 'Correcao-EFD-Contribuicoes', 'auditoria-am': 'Auditoria-ICMS-AM' }[tipo] || 'Painel-NFSe';
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
  if (empresa.validade && new Date(empresa.validade) < new Date()) {
    return { error: `O certificado dessa empresa está VENCIDO desde ${empresa.validade.split('-').reverse().join('/')} — remova e cadastre um certificado válido antes de baixar.`, tipo: 'pulada' };
  }
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde salvar os documentos antes de baixar.', tipo: 'pulada' };

  const senhaPath = path.join(_certDir(), `${empresa.id}.senha`);
  if (!fs.existsSync(senhaPath)) return { error: 'Senha do certificado não encontrada — cadastre a empresa novamente.', tipo: 'pulada' };
  let senha;
  try { senha = safeStorage.decryptString(fs.readFileSync(senhaPath)); }
  catch (e) { return { error: 'Não consegui ler a senha salva com segurança nesta máquina.', tipo: 'pulada' }; }

  const pfxPath = path.join(_certDir(), empresa.pfxArquivo);
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
    return resultado.erro ? { error: resultado.erro, tipo: 'erro' } : { ok: true, resultado };
  } catch (e) { return { error: String(e.message || e), tipo: 'erro' }; }
}

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
      salvarPainel: (emp, html) => nfseLote.salvarPainelIndividual(pastaBase, emp, html, dataInicial, dataFinal),
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
      caminho, pasta_relatorios: [pastaBase, '<Empresa>', 'NFS-e', 'Relatórios', sub].join(path.sep) + path.sep, empresas: resultados,
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
  const pastaEmpresa = path.join(pastaBase, empresa.razaoSocial);
  const jsonTmp = path.join(os.tmpdir(), `fc_nfse_pdf_${Date.now()}.json`);
  try {
    await runFiscal(['nfse-pdf-chave', pastaEmpresa, chave, '--json', jsonTmp], jsonTmp);
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
  try { return { ok: true, itens: await cloud.listLicenses(app.getPath('userData')) }; }
  catch (e) { return { error: String(e.message || e) }; }
});
ipcMain.handle('license:setStatus', async (_evt, { codigo, status }) => {
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
const _SISTEMA_CHAT_IA = `Você é o assistente tributário interno da Liddera | Inteligência em Negócios, um escritório de contabilidade brasileiro. Ajuda a equipe do escritório com dúvidas de ICMS (com atenção especial a Acre, Rondônia, Amazonas, São Paulo e Mato Grosso — os estados onde a Liddera mais atua), PIS/COFINS, e a Reforma Tributária (IBS/CBS, Lei Complementar 214/2025 e normas relacionadas).

Portais oficiais pra buscar primeiro, por estado (sempre que a pergunta for de ICMS estadual, inclua o domínio na busca, tipo "RICMS combustível site:sefaz.ac.gov.br"):
- Acre: sefaz.ac.gov.br
- Rondônia: sefin.ro.gov.br
- Amazonas: sefaz.am.gov.br
- São Paulo: portal.fazenda.sp.gov.br e legislacao.fazenda.sp.gov.br (texto do RICMS/SP)
- Mato Grosso: sefaz.mt.gov.br
Pra PIS/COFINS e regras federais: gov.br/receitafederal ou receita.fazenda.gov.br. Pra Reforma Tributária (IBS/CBS): gov.br/receitafederal, planalto.gov.br (texto de lei), e confaz.fazenda.gov.br. Se a busca nesses domínios não trouxer nada e for preciso usar outra fonte, prefira sempre official (.gov.br) antes de blog/site terceiro.

Isso é um CHAT, dentro de um painel estreito (370px) — não um relatório nem um parecer técnico. Formato da resposta:
- PRIMEIRA FRASE = a resposta em si. Nunca abra com "Ótimo", "Já tenho o suficiente", "Aqui vai", "---", ou qualquer frase de transição/preâmbulo — isso não é permitido, nem uma vez.
- Responda EXATAMENTE o que foi perguntado, nada além. Se perguntarem "é X ou é Y", a primeira frase precisa dizer "é X" ou "é Y" (ou "não achei confirmação clara sobre isso") — não uma explicação de contexto antes de chegar lá.
- Sem títulos, sem ###, sem tabela markdown, sem lista de bullets longa. Texto corrido, em parágrafos curtos — no máximo 2 ou 3 parágrafos curtos no total, como uma resposta de WhatsApp bem escrita, não um documento.
- Cite a fonte de forma breve e natural dentro do texto (ex.: "conforme o RICMS/AC" ou "segundo a SEFAZ-RO"), sem seção dedicada de referências.

Sobre incerteza (isso é o que mais precisa mudar): quando não achar confirmação clara de algo, diga isso em UMA frase curta e pare — nunca escreva um parágrafo explicando o raciocínio da dúvida (decretos que mudaram outra coisa, MVA de categoria genérica, "vale checar direto na SEFAZ"). Errado: um parágrafo listando o que foi encontrado, o que não foi, e por quê. Certo: "Sobre ST, não achei confirmação de que o papel higiênico tem CEST específico no Anexo I — precisa confirmar direto na SEFAZ-AC." Uma frase, sem justificar o processo de busca.

Regras de conteúdo (o rigor continua o mesmo, só a forma de apresentar muda):
- Antes de citar uma alíquota, prazo, ou regra específica, BUSQUE a informação na fonte oficial (SEFAZ do estado, Receita Federal, Confaz) em vez de responder só da memória — tributário muda com frequência e uma resposta desatualizada pode gerar problema real pro escritório ou pro cliente.
- Sempre que o assunto envolver a Reforma Tributária, sinalize em poucas palavras se aquele ponto já está definido em lei ou ainda depende de regulamentação futura — a transição vai até 2033.
- Não invente uma resposta definitiva pra parecer mais útil — se a fonte não confirma, diga isso claramente (numa frase, como acima) em vez de arriscar.
- Você é apoio à pesquisa do time interno, não a palavra final — mas não repita esse aviso a cada resposta.`;

ipcMain.handle('ia:enviarMensagem', async (_evt, { mensagem, historico }) => {
  let chave;
  try {
    chave = await cloud.getChaveIA();
  } catch (e) {
    return { error: String(e.message || e) };
  }
  try {
    const messages = [...(historico || []), { role: 'user', content: mensagem }];
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': chave,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1500,
        system: _SISTEMA_CHAT_IA,
        messages,
        tools: [{ type: 'web_search_20250305', name: 'web_search' }],
      }),
    });
    if (!resp.ok) {
      const errTxt = await resp.text().catch(() => '');
      return { error: `Erro na API (${resp.status}): ${errTxt.slice(0, 200)}` };
    }
    const data = await resp.json();
    const texto = (data.content || [])
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('\n');
    return { ok: true, texto, resposta: { role: 'assistant', content: data.content } };
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
ipcMain.handle('updater:installNow', () => { updater.installNow(); });

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
function fiscalRunner() {
  if (app.isPackaged) {
    const bin = process.platform === 'win32' ? 'fiscal_core.exe' : 'fiscal_core';
    return { cmd: path.join(process.resourcesPath, 'bin', bin), base: [] };
  }
  const { cmd } = pythonCore(); // interpretador Python do venv em dev
  return { cmd, base: [fiscalScriptPath()] };
}

function runFiscal(cliArgs, readyFile) {
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
    const timer = setInterval(() => {
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
function _soAdmin() { return sessionRole === 'admin' ? null : { error: 'Acesso restrito ao Admin.' }; }
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

ipcMain.handle('admin:audPick', async () => {
  const bloq = _soAdmin(); if (bloq) return bloq;
  const r = await dialog.showOpenDialog(mainWindow, { title: 'Selecione a EFD ICMS/IPI (SPED Fiscal) do cliente do Amazonas',
    properties: ['openFile', 'multiSelections'], filters: [{ name: 'SPED Fiscal', extensions: ['txt'] }] });
  if (r.canceled || !r.filePaths.length) return { canceled: true };
  return { paths: r.filePaths };
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

ipcMain.handle('fiscal:corrigirSped', async (_evt, { spedPath, cestInvalidos }) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const saidaTmp = path.join(os.tmpdir(), `fc_corrigido_${Date.now()}.txt`);
  const resumoTmp = path.join(os.tmpdir(), `fc_resumo_${Date.now()}.json`);
  try {
    const cestArg = (cestInvalidos || []).filter(Boolean).join(',');
    const args = ['corrigir', spedPath, '--saida', saidaTmp, '--json', resumoTmp];
    if (cestArg) args.push('--cest', cestArg);
    await runFiscal(args, saidaTmp);
    const resumo = JSON.parse(fs.readFileSync(resumoTmp, 'utf-8'));
    fs.unlink(resumoTmp, () => {});
    if (lastSpedCorrigidoPath) fs.unlink(lastSpedCorrigidoPath, () => {});
    lastSpedCorrigidoPath = saidaTmp;
    return { ok: true, resumo };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:corrigirSpedDashboard', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
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

ipcMain.handle('fiscal:efdCorrigir', async (_evt, spedPath, pvaPath) => {
  if (!spedPath) return { error: 'Selecione o arquivo da EFD-Contribuições.' };
  const stamp = Date.now();
  const htmlOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.html`);
  const jsonOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.json`);
  const txtOut = path.join(os.tmpdir(), `fc_efdcorr_${stamp}.txt`);
  try {
    const args = ['efd-corrigir', spedPath, '--saida', txtOut, '--painel-html', htmlOut, '--json', jsonOut];
    if (pvaPath) args.push('--pva', pvaPath);
    await runFiscal(args, jsonOut);
    const resumo = JSON.parse(fs.readFileSync(jsonOut, 'utf-8'));
    if (resumo.erro) return { error: resumo.erro };
    const painelHtml = fs.readFileSync(htmlOut, 'utf-8');
    [htmlOut, jsonOut].forEach((p) => fs.unlink(p, () => {}));
    return { ok: true, resumo, painelHtml, corrigidoPath: txtOut };
  } catch (e) { return { error: String(e.message || e) }; }
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

ipcMain.handle('fiscal:dashboard', async (_evt, spedPath) => {
  if (!spedPath) return { error: 'Selecione o SPED.' };
  const htmlOut = path.join(os.tmpdir(), `fc_sped_${Date.now()}.html`);
  try {
    await runFiscal(['sped', spedPath, '--dashboard-html', htmlOut], htmlOut);
    const html = fs.readFileSync(htmlOut, 'utf-8');
    fs.unlink(htmlOut, () => {});
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
    } catch (_) {}
    fs.unlink(jsonOut, () => {}); fs.unlink(htmlOut, () => {});
    return { ok: true, html, resumo };
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
