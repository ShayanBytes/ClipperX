@echo off
setlocal
cd /d "%~dp0"
title ClipperX Desktop
if not exist "node_modules\electron" call npm install --no-audit --no-fund
if errorlevel 1 goto :error
call npm run doctor
if errorlevel 1 (
  echo.
  echo Engine setup is incomplete. Repairing automatically...
  call npm run setup:engine
  if errorlevel 1 goto :error
  call npm run doctor
  if errorlevel 1 goto :error
)
call npm run desktop
exit /b 0
:error
echo.
echo ClipperX could not start. The Hermes agent Python was ignored; install a normal Python 3.11 with pip if setup could not find one.
pause
exit /b 1
