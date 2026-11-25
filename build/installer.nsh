; FiscoCont+ — antes de instalar ou desinstalar, encerra os núcleos que ainda estiverem abertos.
; Sem isso, um núcleo aberto trava os arquivos e aparece "Falha ao desinstalar os arquivos do aplicativo antigo".
; O próprio FiscoCont+.exe NÃO é encerrado aqui: o instalador do electron-builder já fecha o aplicativo, e matar
; a árvore de processos do app (taskkill /T) matava também o instalador, que é filho dele (achado real, 25/10/2026:
; "ao clicar em atualizar, o sistema fecha e não instala nada").
!macro _fcEncerra
  nsExec::Exec 'taskkill /F /IM balancete_core.exe'
  nsExec::Exec 'taskkill /F /IM fiscal_core.exe'
  nsExec::Exec 'taskkill /F /IM extrato_core.exe'
  Sleep 500
!macroend

; 2.4.53: "Falha ao desinstalar os arquivos do aplicativo antigo ...: 2" — sobrava FiscoCont+.exe aberto (robô da fila
; ou processo da GPU/renderer). Encerra só os processos com esse nome, SEM /T: o instalador é outro executável e,
; sem /T, não é derrubado junto (o problema de 25/10/2026 era o /T). Depois espera o Windows soltar os arquivos.
!macro _fcEncerraApp
  nsExec::Exec 'taskkill /F /IM "FiscoCont+.exe"'
  Sleep 1500
!macroend

!macro customInit
  !insertmacro _fcEncerra
  !insertmacro _fcEncerraApp
!macroend

!macro customUnInit
  !insertmacro _fcEncerra
!macroend
