@echo off
setlocal
cd /d "%~dp0"
title FiscoCont+
if not exist "package.json" ( if exist "FiscoCont\package.json" cd /d "%~dp0FiscoCont" )
if not exist "package.json" (
  echo [ERRO] package.json nao encontrado.
  echo Coloque este run-dev.bat dentro da pasta do FiscoCont+ e rode de novo.
  echo Pasta atual: %CD%
  if not defined FISCOCONT_SILENT pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Node.js nao encontrado no PATH.
  echo Rode o instalar.bat ^(ou instalar-portatil.bat^) primeiro.
  if not defined FISCOCONT_SILENT pause
  exit /b 1
)

if not exist "node_modules" (
  echo Instalando dependencias Node ^(baixa o Electron, ~150 MB - pode levar alguns minutos na 1a vez^)...
  echo ^(nao feche esta janela mesmo se parecer parado^)
  set "npm_config_progress=false"
  set "npm_config_loglevel=info"
  call npm install
  if errorlevel 1 ( echo [ERRO] npm install falhou. Veja a mensagem acima. & if not defined FISCOCONT_SILENT pause & exit /b 1 )
)
if not exist "node_modules\firebase-admin" (
  echo Instalando dependencia nova ^(nuvem^)...
  set "npm_config_progress=false"
  set "npm_config_loglevel=info"
  call npm install
  if errorlevel 1 ( echo [ERRO] npm install falhou. Veja a mensagem acima. & if not defined FISCOCONT_SILENT pause & exit /b 1 )
)
if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Ambiente Python ^(.venv^) nao encontrado.
  echo Rode o instalar.bat ^(ou instalar-portatil.bat^) primeiro.
  if not defined FISCOCONT_SILENT pause
  exit /b 1
)

REM usa o Python do .venv (assinado) para ler o PDF
set "FISCOCONT_PYTHON=%CD%\.venv\Scripts\python.exe"
echo Abrindo o FiscoCont+ ...
echo ^(pasta: %CD%^)
call npm start
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo ==========================================================
  echo   O FiscoCont+ fechou com um erro ^(codigo %RC%^).
  echo   Role para cima e veja a mensagem em vermelho/texto acima.
  echo   Se nao souber o que fazer, mande um print desta janela.
  echo ==========================================================
  if not defined FISCOCONT_SILENT pause
)
exit /b %RC%
