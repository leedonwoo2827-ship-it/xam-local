@echo off
REM ---------------------------------------------------------------------------
REM XAM LOCAL - RESTART. Kills whatever holds the port, then starts fresh.
REM
REM Why this exists (and why run.bat cannot do it):
REM   The app has no --reload. Editing Python (services\, routes\, core\) does
REM   NOT take effect until the server restarts. Static files (static\js,
REM   static\css) DO reload on F5 - those never need this.
REM
REM   That gap bit us: the publish checklist gained a step, the browser was
REM   refreshed, and the step was not there. The screen looked broken instead
REM   of stale. So restarting must be one double-click, not a hunt for the
REM   right console window.
REM
REM   run.bat refuses to start when the port is busy - on purpose, so it never
REM   silently fights another instance. This file is the deliberate override.
REM
REM ASCII ONLY. Flat IF + GOTO. Override the port with:  set PORT=8871 && rerun.bat
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8870"

if not exist "venv\Scripts\python.exe" goto :noinstall

echo.
echo   XAM LOCAL  -  RESTART on port %PORT%
echo.

REM --- 1. kill the current holder ------------------------------------------
REM  Match LISTENING only. A browser's outbound socket to the same port shows
REM  up as ESTABLISHED and killing that would take down the browser.
REM  The trailing space in ":%PORT% " stops :8870 from matching :88700.
set "PID="
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /r /c:"LISTENING" ^| findstr /c:":%PORT% "') do set "PID=%%p"

if not defined PID goto :nothing
echo   Stopping PID %PID% ...
taskkill /f /pid %PID% >nul 2>&1
if errorlevel 1 goto :killfail

REM Windows holds the socket briefly after the process dies. Without this wait
REM uvicorn can still hit "address already in use" and exit immediately.
timeout /t 2 >nul
echo   Stopped.
goto :start

:nothing
echo   Nothing was running on %PORT%. Starting fresh.
goto :start

:start
echo.
echo   KEEP THIS WINDOW OPEN. It is the server.
echo   Closing it stops the app and any render in progress.
echo.
start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%PORT%/"
venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port %PORT%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" echo   Server stopped.
if not "%RC%"=="0" echo   [ERROR] Server exited with code %RC%. Read the lines above.
goto :hold

:killfail
echo.
echo   [ERROR] Could not stop PID %PID%.
echo.
echo   It may belong to another user, or a render subprocess is holding it.
echo   Close the XAM LOCAL console window by hand, then run this again.
goto :hold

:noinstall
echo.
echo   [ERROR] venv not found. Run setup.bat first.
goto :hold

:hold
echo.
pause
exit /b 0
