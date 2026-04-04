; ─────────────────────────────────────────────────────────────────────
; Trading Journal Windows Installer (NSIS)
;
; Usage:
;   1. Download NSIS from https://nsis.sourceforge.io/
;   2. Run: "C:\Program Files (x86)\NSIS\makensis.exe" build_installer_windows.nsi
;   3. Produces: dist/TradingJournal_Setup.exe
; ─────────────────────────────────────────────────────────────────────

!include "MUI2.nsh"

; Basic settings
Name "Trading Journal"
OutFile "dist\TradingJournal_Setup.exe"
InstallDir "$PROGRAMFILES\TradingJournal"
InstallDirRegKey HKLM "Software\TradingJournal" "InstallLocation"

; Request admin privileges
RequestExecutionLevel admin

; MUI Settings
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

; Installer sections
Section "Install"
  SetOutPath "$INSTDIR"

  ; Copy files from PyInstaller output
  File /r "dist\TradingJournal\*.*"

  ; Create Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\Trading Journal"
  CreateShortCut "$SMPROGRAMS\Trading Journal\Trading Journal.lnk" "$INSTDIR\TradingJournal.exe"
  CreateShortCut "$SMPROGRAMS\Trading Journal\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Create Desktop shortcut
  CreateShortCut "$DESKTOP\Trading Journal.lnk" "$INSTDIR\TradingJournal.exe"

  ; Write registry for uninstall
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingJournal" "DisplayName" "Trading Journal"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingJournal" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingJournal" "DisplayIcon" "$INSTDIR\TradingJournal.exe"
  WriteRegStr HKLM "Software\TradingJournal" "InstallLocation" "$INSTDIR"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

; Uninstaller section
Section "Uninstall"
  ; Remove files
  RMDir /r "$INSTDIR"

  ; Remove Start Menu shortcuts
  RMDir /r "$SMPROGRAMS\Trading Journal"

  ; Remove Desktop shortcut
  Delete "$DESKTOP\Trading Journal.lnk"

  ; Remove registry
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingJournal"
  DeleteRegKey HKLM "Software\TradingJournal"
SectionEnd
