@echo off
setlocal
cd /d "%~dp0"
title ClipperX Web Test Server
echo.
echo ClipperX Web Test Mode - no desktop installation required
echo Keep this window open while testing.
echo.
where node >nul 2>nul || (echo Node.js is not installed or not on PATH.& goto :error)
where npm >nul 2>nul || (echo npm is not installed or not on PATH.& goto :error)
if not exist "node_modules\vite" (
  echo [First web run only] Installing JavaScript dependencies...
  call npm install --no-audit --no-fund
  if errorlevel 1 goto :error
) else (
  echo JavaScript dependencies already present - skipping installation.
)
call npm run doctor >nul 2>nul
if errorlevel 1 (
  echo Checking or repairing the local video engine...
  call npm run setup:engine
  if errorlevel 1 goto :error
  call npm run doctor
  if errorlevel 1 goto :error
)
echo.
echo Starting ClipperX at http://localhost:5173
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:5173"
call npm run dev
exit /b 0
:error
echo.
echo WEB TEST MODE COULD NOT START. Read the first error above.
pause
exit /b 1
