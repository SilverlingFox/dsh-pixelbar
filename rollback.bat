@echo off
chcp 65001 >nul
where pwsh >nul 2>nul && (pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0rollback.ps1") || (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0rollback.ps1")
pause
