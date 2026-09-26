'use strict';
// Atualização automática do FiscoCont+.
//
// Fica "pronta, porém inerte" até o package.json ter uma seção "publish"
// configurada (GitHub Releases, ou um servidor genérico) — sem isso, o
// electron-updater simplesmente não acha onde procurar e a checagem falha
// em silêncio (nunca trava nem incomoda ninguém).
//
// O require('electron-updater') é feito SÓ NA HORA DE USAR (dentro das
// funções, não no topo do arquivo) de propósito: esse pacote acessa o app
// do Electron assim que é carregado, e se isso falhar por qualquer motivo
// não pode derrubar o sistema inteiro — o app sempre tem que abrir.

let wired = false;

function _autoUpdater() {
  return require('electron-updater').autoUpdater;
}

function initAutoUpdate(getMainWindow) {
  if (wired) return;
  try {
    const autoUpdater = _autoUpdater();
    wired = true;

    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;

    const send = (canal, payload) => {
      const win = getMainWindow();
      if (win && !win.isDestroyed()) win.webContents.send(canal, payload);
    };

    autoUpdater.on('update-available', (info) => {
      send('updater:available', { versao: info.version });
    });
    autoUpdater.on('update-downloaded', (info) => {
      send('updater:ready', { versao: info.version });
    });
    autoUpdater.on('error', () => {
      // silencioso de propósito: falha de atualização nunca deve atrapalhar
      // o trabalho do dia — só significa que não há update configurado/disponível.
    });
  } catch (_) {
    // sem "publish" configurado, ou qualquer outro problema: recurso fica inerte.
  }
}

async function checkNow() {
  try { await _autoUpdater().checkForUpdates(); } catch (_) { /* silencioso */ }
}

function installNow() {
  try { _autoUpdater().quitAndInstall(); } catch (_) {}
}

module.exports = { initAutoUpdate, checkNow, installNow };
