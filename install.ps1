# Trading Journal — Windows desktop integration
#
# Usage (run from PowerShell in the TradingJournal folder):
#   .\install.ps1            — create Start Menu shortcut (+ optional Desktop)
#   .\install.ps1 -Uninstall — remove shortcuts
#
# NOTE: If you move this folder after installing, re-run this script
#       so the shortcut paths are updated.

param([switch]$Uninstall)

$AppDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AppExe    = Join-Path $AppDir "TradingJournal.exe"
$StartMenu = [System.IO.Path]::Combine(
                 $env:APPDATA,
                 "Microsoft\Windows\Start Menu\Programs")
$LnkStart  = Join-Path $StartMenu "Trading Journal.lnk"
$LnkDesk   = Join-Path ([Environment]::GetFolderPath('Desktop')) "Trading Journal.lnk"

function New-AppShortcut($Path) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Path)
    $sc.TargetPath       = $AppExe
    $sc.WorkingDirectory = $AppDir
    $sc.Description      = "Personal trading journal and performance analytics"
    # Icon is embedded in the exe — no need to set IconLocation
    $sc.Save()
}

if ($Uninstall) {
    $removed = $false
    foreach ($lnk in @($LnkStart, $LnkDesk)) {
        if (Test-Path $lnk) {
            Remove-Item $lnk -Force
            Write-Host "  Removed: $lnk"
            $removed = $true
        }
    }
    if ($removed) {
        Write-Host ""
        Write-Host "Done. You can now delete the TradingJournal folder."
    } else {
        Write-Host "Nothing to remove (shortcuts were not found)."
    }
    exit
}

# ── Install ──

if (-not (Test-Path $AppExe)) {
    Write-Error "Executable not found: $AppExe"
    exit 1
}

Write-Host "Installing Trading Journal desktop integration..."

New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
New-AppShortcut $LnkStart
Write-Host "  Start Menu shortcut created."

$ans = Read-Host "  Also create a Desktop shortcut? [y/N]"
if ($ans -match '^[Yy]') {
    New-AppShortcut $LnkDesk
    Write-Host "  Desktop shortcut created."
}

Write-Host ""
Write-Host "Done. Trading Journal is now available in the Start Menu."
Write-Host ""
Write-Host "NOTE: If you move this folder, re-run this script to update the shortcuts."
