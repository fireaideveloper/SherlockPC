; Current-user installation. Preserve registration during /UPDATE upgrades.
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $UpdateMode <> 1
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "SherlockPC"
  ${EndIf}
!macroend
