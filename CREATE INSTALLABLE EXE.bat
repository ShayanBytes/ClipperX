@echo off
setlocal
cd /d "%~dp0"
title Create ClipperX Windows Installer
set "CSC_IDENTITY_AUTO_DISCOVERY=false"
set "CLIPPERX_UNSIGNED_WINDOWS_BUILD=1"
where node >nul 2>nul || (echo Node.js is not installed or not on PATH.& goto :error)
where npm >nul 2>nul || (echo npm is not installed or not on PATH.& goto :error)
echo [1/6] Installing desktop build tools...
call npm install --no-audit --no-fund
if errorlevel 1 goto :error
echo [2/6] Installing the Python video engine...
call npm run setup:engine
if errorlevel 1 goto :error
echo [3/6] Checking FFmpeg, Python, and required modules...
call npm run doctor
if errorlevel 1 goto :error
echo [4/6] Running engine tests...
call npm run test:engine
if errorlevel 1 goto :error
echo [5/6] Validating the unsigned Windows release configuration...
call npm run release:check
if errorlevel 1 goto :error
echo [6/6] Building the installable Windows EXE...
echo Code-signing resource editing is disabled so standard Windows accounts do not need symbolic-link privileges.
call npm run desktop:installer
if errorlevel 1 goto :error
for %%F in ("release\ClipperX-Setup-*.exe") do set "INSTALLER=%%~fF"
if not defined INSTALLER (echo Installer was not found in release.& goto :error)
echo.
echo SUCCESS: %INSTALLER%
echo This is an unsigned local build. Windows SmartScreen may show More info ^> Run anyway.
start "" explorer.exe /select,"%INSTALLER%"
pause
exit /b 0
:error
echo.
echo BUILD FAILED. Read the first error above.
echo If an old electron-builder cache is mentioned, delete %%LOCALAPPDATA%%\electron-builder\Cache\winCodeSign and retry this file.
echo A browser is never used by the installed app.
pause
exit /b 1
