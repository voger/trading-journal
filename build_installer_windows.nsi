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
!define VERSION "3.3.0"
!define PRODUCT_NAME "Trading Journal"
!define PRODUCT_PUBLISHER "Trading Journal Contributors"

Name "${PRODUCT_NAME} v${VERSION}"
OutFile "dist\TradingJournal_Setup.exe"
InstallDir "$PROGRAMFILES\${PRODUCT_NAME}"
InstallDirRegKey HKLM "Software\${PRODUCT_NAME}" "InstallLocation"

; Request admin privileges
RequestExecutionLevel admin

; MUI Settings
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

; Installer sections
Section "$(^NameDA)" SEC_INSTALL
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; Copy files from PyInstaller output
  File /r "dist\TradingJournal\*.*"

  ; Copy license
  File "LICENSE"

  ; Write registry for uninstall
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_NAME} v${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayIcon" "$INSTDIR\TradingJournal.exe"
  WriteRegStr HKLM "Software\${PRODUCT_NAME}" "InstallLocation" "$INSTDIR"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "$(^StartMenuFolder)" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\TradingJournal.exe"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop Shortcut" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\TradingJournal.exe"
SectionEnd

; Uninstaller section
Section "Uninstall"
  ; Remove files
  RMDir /r "$INSTDIR"

  ; Remove Start Menu shortcuts
  RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Remove Desktop shortcut
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  ; Remove registry
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
  DeleteRegKey HKLM "Software\${PRODUCT_NAME}"
SectionEnd

; Install options descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_INSTALL} "Trading Journal application files (required)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} "Create shortcuts in the Start Menu"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} "Create a shortcut on the Desktop"
!insertmacro MUI_FUNCTION_DESCRIPTION_END
