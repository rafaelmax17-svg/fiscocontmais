@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
if not exist "package.json" ( if exist "FiscoCont\package.json" cd /d "%~dp0FiscoCont" )
if not exist "package.json" (
  echo [ERRO] package.json nao encontrado. Rode este .bat na pasta do projeto ^(ou na de cima^).
  echo Pasta atual: %CD%
  pause & exit /b 1
)

title FiscoCont+ :: instalador
echo ==========================================================
echo   FiscoCont+  -  INSTALADOR
echo   Prepara Node/Python e deixa o app pronto para usar.
echo   ^(Nao gera Setup.exe - roda direto, sem instalador^)
echo ==========================================================
echo Projeto: %CD%
echo.

set "INSTALOU=0"

REM ---------------- Node.js ----------------
where node >nul 2>nul
if errorlevel 1 (
  echo [*] Node.js nao encontrado.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ERRO] Sem Node.js e sem winget. Instale o Node.js LTS em https://nodejs.org
    echo e rode este arquivo de novo.
    pause & exit /b 1
  )
  echo     Instalando Node.js LTS via winget...
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  set "INSTALOU=1"
) else (
  echo [ok] Node.js ja instalado.
)

REM ---------------- Python real (ignora stub da Store) ----------------
set "PYCMD="
py -3 --version >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD (
  echo [*] Python nao encontrado.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ERRO] Sem Python e sem winget. Instale o Python 3.12 em
    echo https://www.python.org/downloads/ marcando "Add Python to PATH", e rode de novo.
    pause & exit /b 1
  )
  echo     Instalando Python 3.12 via winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  set "INSTALOU=1"
) else (
  echo [ok] Python ja instalado ^(!PYCMD!^).
)

if "!INSTALOU!"=="1" (
  echo.
  echo ==========================================================
  echo   Node e/ou Python acabaram de ser instalados.
  echo   FECHE esta janela e rode o instalar.bat de novo
  echo   ^(o Windows precisa recarregar o PATH^).
  echo ==========================================================
  pause
  exit /b 0
)

echo [ok] Node e Python prontos ^(Python: !PYCMD!^).
echo.

REM ---------------- libera os arquivos (tira marca de "baixado da internet") ----------------
echo [1/4] Liberando arquivos ^(removendo marca de download, se houver^)...
powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%CD%' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>nul

REM ---------------- dependencias Node ----------------
echo [2/4] Instalando dependencias Node ^(baixa o Electron, ~150 MB - pode levar alguns minutos na 1a vez^)...
echo       Nao feche esta janela mesmo se parecer parado; o download continua em segundo plano.
set "npm_config_progress=false"
set "npm_config_loglevel=info"
call npm install || ( echo [ERRO] npm install falhou. & pause & exit /b 1 )

REM ---------------- ambiente Python (.venv) ----------------
echo.
echo [3/4] Preparando ambiente Python ^(.venv^)...
if not exist ".venv" ( %PYCMD% -m venv .venv || ( echo [ERRO] Falha ao criar venv. & pause & exit /b 1 ) )
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r "python\requirements.txt" || ( echo [ERRO] pip install falhou. & pause & exit /b 1 )
call ".venv\Scripts\deactivate.bat"

REM ---------------- icones + atalho na area de trabalho ----------------
echo.
echo [4/4] Criando icones e atalho na Area de Trabalho...
call npm run icons >nul 2>nul
set "LNK=%USERPROFILE%\Desktop\FiscoCont+.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath=[Environment]::ExpandEnvironmentVariables('%SystemRoot%\System32\wscript.exe'); $s.Arguments='\"%CD%\run-hidden.vbs\"'; $s.WorkingDirectory='%CD%'; if(Test-Path '%CD%\build\icon.ico'){$s.IconLocation='%CD%\build\icon.ico'}; $s.Save()" >nul 2>nul
set "LNK2=%USERPROFILE%\Desktop\FiscoCont+ (diagnostico).lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK2%'); $s.TargetPath='%CD%\run-dev.bat'; $s.WorkingDirectory='%CD%'; $s.WindowStyle=1; if(Test-Path '%CD%\build\icon.ico'){$s.IconLocation='%CD%\build\icon.ico'}; $s.Save()" >nul 2>nul

echo.
echo ==========================================================
echo   PRONTO!
echo   Criei 2 atalhos na Area de Trabalho:
echo     - "FiscoCont+"              abre direto, sem janela preta
echo     - "FiscoCont+ (diagnostico)" abre mostrando a tela do console
echo                                  ^(use se algo nao funcionar^)
echo   Abra por ele ^(ou rode run-dev.bat nesta pasta^) para usar.
echo ==========================================================
echo.
echo Abrindo o FiscoCont+ ...
start "" "%CD%\run-dev.bat"
pause
exit /b 0
