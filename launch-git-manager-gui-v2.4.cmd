@echo off
setlocal
set "SCRIPT=%~dp0aerial-git-manager-gui-v2.4-portable.ps1"

if not exist "%SCRIPT%" (
    echo ERROR: The GUI PowerShell file was not found:
    echo %SCRIPT%
    echo.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%SCRIPT%"
