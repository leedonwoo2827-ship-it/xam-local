@echo off
REM ---------------------------------------------------------------------------
REM XAM LOCAL - one time setup
REM
REM ASCII ONLY on purpose. Non-ASCII in a .bat breaks on CP949 consoles.
REM Flat structure: single-line IFs + GOTO labels. No nested () blocks and no
REM self-relaunch - both have bitten this project before.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "LOG=setup_log.txt"
echo XAM LOCAL setup %DATE% %TIME% > "%LOG%"

echo.
echo [1/4] looking for Python...
set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :havepy
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :havepy
goto :nopy

:havepy
echo       found: %PY%
%PY% --version >> "%LOG%" 2>&1

echo.
echo [2/4] creating venv...
if exist "venv\Scripts\python.exe" goto :haveenv
%PY% -m venv venv >> "%LOG%" 2>&1
if errorlevel 1 goto :novenv
:haveenv
echo       ok: venv\Scripts\python.exe

echo.
echo [3/4] installing packages...
venv\Scripts\python -m pip install --upgrade pip >> "%LOG%" 2>&1
venv\Scripts\python -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 goto :pipfail
echo       ok

echo.
echo [4/4] checking external trees...
if exist ".env" goto :haveenvfile
if exist ".env.example" copy /y ".env.example" ".env" >nul
echo       created .env from .env.example - review it
:haveenvfile

if exist "D:\00work\ocr-output-260730\_rounds\m01.json" goto :bookok
echo       WARNING: BOOK not found at D:\00work\ocr-output-260730
echo                set XAM_BOOK in .env
goto :chodangi
:bookok
echo       BOOK ok

:chodangi
if exist "D:\00work\chodangi-mp4-forge-main\make_bundle_video.py" goto :chodok
echo       WARNING: chodangi-mp4-forge not found - video render disabled
echo                set XAM_CHODANGI in .env
goto :axexam
:chodok
echo       chodangi ok

:axexam
if exist "_ref\axexam\scripts\build_check.py" goto :axok
echo       NOTE: _ref\axexam not cloned yet - publish build disabled
echo             git clone https://github.com/leedonwoo2827-ship-it/axexam _ref\axexam
goto :done
:axok
echo       axexam ok

:done
echo.
echo ===========================================
echo  setup finished. now run:  run.bat
echo ===========================================
echo.
pause
exit /b 0

:nopy
echo.
echo [ERROR] Python 3 not found.
echo         Install Python 3.11+ from python.org and check "Add to PATH".
echo.
pause
exit /b 1

:novenv
echo.
echo [ERROR] failed to create venv. see %LOG%
echo.
pause
exit /b 1

:pipfail
echo.
echo [ERROR] pip install failed. see %LOG%
echo         Most common cause: no network, or a proxy blocking pypi.org.
echo.
pause
exit /b 1
