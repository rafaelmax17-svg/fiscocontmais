; FiscoCont+ — antes de instalar ou desinstalar, encerra o sistema e os núcleos que ainda estiverem abertos.
; Sem isso, um núcleo aberto trava os arquivos e aparece "Falha ao desinstalar os arquivos do aplicativo antigo".
!macro _fcEncerra
  nsExec::Exec 'taskkill /F /T /IM "FiscoCont+.exe"'
  nsExec::Exec 'taskkill /F /T /IM balancete_core.exe'
  nsExec::Exec 'taskkill /F /T /IM fiscal_core.exe'
  nsExec::Exec 'taskkill /F /T /IM extrato_core.exe'
  Sleep 800
!macroend

!macro customInit
  !insertmacro _fcEncerra
!macroend

!macro customUnInit
  !insertmacro _fcEncerra
!macroend
