; Kill any running Sparkbot instance before files are extracted,
; so the installer never hits "file in use" errors.
!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Closing Sparkbot if it is running..."
  nsExec::ExecToLog 'cmd /C taskkill /F /IM "sparkbot-local-shell.exe" /T >nul 2>&1'
  nsExec::ExecToLog 'cmd /C taskkill /F /IM "Sparkbot Local.exe" /T >nul 2>&1'
  nsExec::ExecToLog 'cmd /C taskkill /F /IM "sparkbot-backend.exe" /T >nul 2>&1'
  Sleep 1500
!macroend
