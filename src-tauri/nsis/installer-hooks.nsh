; Kill any running Sparkbot instance before files are extracted,
; so the installer never hits "file in use" errors.
!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Closing Sparkbot if it is running..."
  nsExec::ExecToLog 'taskkill /F /IM "Sparkbot Local.exe" /T'
  nsExec::ExecToLog 'taskkill /F /IM "sparkbot-backend.exe" /T'
  Sleep 1500
!macroend
