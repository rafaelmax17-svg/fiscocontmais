'use strict';
const { app, BrowserWindow, ipcMain, dialog, shell, safeStorage } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn } = require('child_process');
const cloud = require('./cloudSync');
const license = require('./license');
const changelog = require('./changelog');
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
  if (process.platform !== 'darwin') app.quit();
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
ipcMain.handle('auth:login', (_evt, senha) => {
  const role = AUTH_SENHAS[String(senha || '')];
  if (!role) return { ok: false };
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

ipcMain.handle('fiscal:pickPastaBase', async () => {
  const res = await dialog.showOpenDialog(mainWindow, { title: 'Escolher pasta onde salvar os documentos', properties: ['openDirectory', 'createDirectory'] });
  if (res.canceled || !res.filePaths.length) return { canceled: true };
  fs.writeFileSync(_configDownloadPath(), JSON.stringify({ pastaBase: res.filePaths[0] }));
  return { canceled: false, path: res.filePaths[0] };
});
ipcMain.handle('fiscal:pastaBaseGet', () => {
  try { return JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase || null; }
  catch (_) { return null; }
});

ipcMain.handle('fiscal:nfseAnalise', async (_evt, { empresaId }) => {
  const indice = _lerIndiceCert();
  const empresa = indice.empresas.find((e) => e.id === empresaId);
  if (!empresa) return { error: 'Empresa não encontrada.' };
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde os documentos são salvos primeiro.' };
  const pastaEmpresa = path.join(pastaBase, empresa.razaoSocial);
  if (!fs.existsSync(pastaEmpresa)) return { error: 'Ainda não tem nenhuma nota baixada dessa empresa nessa pasta.' };

  const painelTmp = path.join(os.tmpdir(), `fc_nfse_painel_${Date.now()}.html`);
  const jsonTmp = path.join(os.tmpdir(), `fc_nfse_analise_${Date.now()}.json`);
  try {
    await runFiscal(['analisar-nfse', pastaEmpresa, '--cnpj', empresa.cnpj, '--empresa', empresa.razaoSocial,
      '--painel-html', painelTmp, '--json', jsonTmp], jsonTmp);
    const resumo = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    const painelHtml = fs.readFileSync(painelTmp, 'utf-8');
    [painelTmp, jsonTmp].forEach((p) => fs.unlink(p, () => {}));
    return { ok: true, resumo, painelHtml };
  } catch (e) { return { error: String(e.message || e) }; }
});

ipcMain.handle('fiscal:nfseExportarHtml', async (_evt, { html, tipo, empresaNome }) => {
  const nomeArquivo = 'Painel-NFSe';
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

ipcMain.handle('fiscal:nfseBaixar', async (_evt, { empresaId, dataInicial, dataFinal }) => {
  const indice = _lerIndiceCert();
  const empresa = indice.empresas.find((e) => e.id === empresaId);
  if (!empresa) return { error: 'Empresa não encontrada — cadastre o certificado primeiro.' };
  if (empresa.validade && new Date(empresa.validade) < new Date()) {
    return { error: `O certificado dessa empresa está VENCIDO desde ${empresa.validade.split('-').reverse().join('/')} — remova e cadastre um certificado válido antes de baixar.` };
  }
  let pastaBase;
  try { pastaBase = JSON.parse(fs.readFileSync(_configDownloadPath(), 'utf-8')).pastaBase; } catch (_) {}
  if (!pastaBase) return { error: 'Escolha a pasta onde salvar os documentos antes de baixar.' };

  const senhaPath = path.join(_certDir(), `${empresaId}.senha`);
  if (!fs.existsSync(senhaPath)) return { error: 'Senha do certificado não encontrada — cadastre a empresa novamente.' };
  let senha;
  try { senha = safeStorage.decryptString(fs.readFileSync(senhaPath)); }
  catch (e) { return { error: 'Não consegui ler a senha salva com segurança nesta máquina.' }; }

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
    await runFiscal(args, jsonTmp);
    const resultado = JSON.parse(fs.readFileSync(jsonTmp, 'utf-8'));
    fs.unlink(jsonTmp, () => {});
    if (!resultado.erro) {
      empresa.ultimoNsu = resultado.ultimo_nsu || empresa.ultimoNsu;
      empresa.ultimoDownload = new Date().toISOString();
      _salvarIndiceCert(indice);
    }
    return resultado.erro ? { error: resultado.erro } : { ok: true, resultado };
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
