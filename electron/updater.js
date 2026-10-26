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
let baixada = false;
let instalando = false;

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

    const atual = () => { try { return require('electron').app.getVersion(); } catch (_) { return ''; } };
    const notas = (info) => {
      const n = info && info.releaseNotes;
      if (!n) return '';
      if (Array.isArray(n)) return n.map((x) => (x && x.note) || '').join('\n');
      return String(n);
    };
    autoUpdater.on('update-available', (info) => {
      send('updater:available', { versao: info.version, atual: atual(), notas: notas(info) });
    });
    autoUpdater.on('download-progress', (p) => {
      send('updater:progress', { pct: p.percent || 0, feito: p.transferred || 0, total: p.total || 0, vel: p.bytesPerSecond || 0 });
    });
    autoUpdater.on('update-downloaded', (info) => {
      baixada = true;
      send('updater:ready', { versao: info.version, atual: atual(), notas: notas(info) });
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

// Instala sempre em silêncio (o instalador do FiscoCont+ é o "assistido": fora do modo silencioso ele pararia na
// tela "Concluir" e não reabriria sozinho). Pelo botão "Atualizar e reiniciar" (comTela = true), antes de fechar
// abre uma janelinha "Atualizando o FiscoCont+…" que some sozinha quando a versão nova abre.
// Chamado uma vez só: chamar de novo (ex.: pelo before-quit) fazia o electron-updater ignorar a instalação.
function installNow(comTela = false, versao = '') {
  if (instalando) return;
  instalando = true;
  if (comTela) { try { _telaInstalando(versao); } catch (_) { /* sem a janelinha, instala igual */ } }
  try { _autoUpdater().quitAndInstall(true, true); } catch (_) { instalando = false; }
}

// Janelinha do Windows (PowerShell + Windows Forms, roda separada do app): fica na frente enquanto o instalador
// troca os arquivos e fecha quando o FiscoCont+ novo abre (ou depois de 3 minutos, por segurança).
function _telaInstalando(versao) {
  if (process.platform !== 'win32') return;
  const os = require('os'), path = require('path'), fs = require('fs'), { spawn } = require('child_process');
  const v = String(versao || '').replace(/[^0-9A-Za-z.\-]/g, '');
  const ps1 = `
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$f = New-Object System.Windows.Forms.Form
$f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.TopMost = $true; $f.ShowInTaskbar = $true
$f.Size = New-Object System.Drawing.Size(440, 156); $f.BackColor = [System.Drawing.Color]::White; $f.Text = 'Atualizando o FiscoCont+'
$faixa = New-Object System.Windows.Forms.Panel; $faixa.BackColor = [System.Drawing.Color]::FromArgb(234, 88, 12)
$faixa.Location = New-Object System.Drawing.Point(0, 0); $faixa.Size = New-Object System.Drawing.Size(440, 5)
$t = New-Object System.Windows.Forms.Label; $t.Text = 'Atualizando o FiscoCont+${v ? ' para a v' + v : ''}'
$t.Font = New-Object System.Drawing.Font('Segoe UI', 13, [System.Drawing.FontStyle]::Bold); $t.ForeColor = [System.Drawing.Color]::FromArgb(15, 23, 42)
$t.AutoSize = $true; $t.Location = New-Object System.Drawing.Point(24, 24)
$s = New-Object System.Windows.Forms.Label; $s.Text = 'N' + [char]0x00E3 + 'o desligue o computador. O sistema abre sozinho em alguns segundos.'
$s.Font = New-Object System.Drawing.Font('Segoe UI', 9); $s.ForeColor = [System.Drawing.Color]::FromArgb(100, 116, 139)
$s.AutoSize = $true; $s.Location = New-Object System.Drawing.Point(26, 60)
$p = New-Object System.Windows.Forms.ProgressBar; $p.Style = 'Marquee'; $p.MarqueeAnimationSpeed = 25
$p.Location = New-Object System.Drawing.Point(26, 100); $p.Size = New-Object System.Drawing.Size(388, 14)
$f.Controls.AddRange(@($faixa, $t, $s, $p))
$script:ini = Get-Date; $script:fase = 0
$tm = New-Object System.Windows.Forms.Timer; $tm.Interval = 700
$tm.Add_Tick({
  $abertos = @(Get-Process -Name 'FiscoCont+' -ErrorAction SilentlyContinue)
  if ($script:fase -eq 0) { if ($abertos.Count -eq 0) { $script:fase = 1 } }
  elseif ($script:fase -eq 1) { if ($abertos.Count -gt 0) { $s.Text = 'Pronto! Abrindo o FiscoCont+...'; $script:fase = 2; $script:fim = Get-Date } }
  elseif (((Get-Date) - $script:fim).TotalSeconds -ge 3) { $tm.Stop(); $f.Close() }
  if (((Get-Date) - $script:ini).TotalSeconds -gt 180) { $tm.Stop(); $f.Close() }
})
$tm.Start()
[void]$f.ShowDialog()
Remove-Item -LiteralPath $PSCommandPath -Force
`;
  const arq = path.join(os.tmpdir(), 'fiscocont-atualizando.ps1');
  fs.writeFileSync(arq, '\ufeff' + ps1, 'utf8');   // BOM: o PowerShell 5 lê os acentos certo
  const ch = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', arq],
    { detached: true, stdio: 'ignore', windowsHide: true });
  ch.unref();
}

function temAtualizacao() { return baixada && !instalando; }

module.exports = { initAutoUpdate, checkNow, installNow, temAtualizacao };
