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
echo [4/5] checking config and bundled engines...
if exist ".env" goto :haveenvfile
if exist ".env.example" copy /y ".env.example" ".env" >nul
echo       created .env from .env.example - review it
:haveenvfile

REM BOOK is chosen in the app (folder panel). .env only holds the first-run default.
if exist "D:\00work\ocr-output-260730\01" goto :bookok
echo       NOTE: default BOOK not found at D:\00work\ocr-output-260730
echo             pick a work folder in the app, or set XAM_BOOK in .env
goto :engine
:bookok
echo       BOOK ok

REM The render engine and the publish builder now live INSIDE this repo.
REM Nothing to clone. Only the two binaries below cannot be bundled.
:engine
if exist "vendor\chodangi\make_bundle_video.py" goto :engok
echo       ERROR: vendor\chodangi is missing - video render will not work
goto :builder
:engok
echo       render engine ok (vendor\chodangi)

:builder
if exist "services\publish\axbuild\build_check.py" goto :bldok
echo       ERROR: services\publish\axbuild is missing - publish build will not work
goto :done4
:bldok
echo       publish builder ok (services\publish\axbuild)

:done4
echo.
echo [5/5] checking things that cannot be bundled...
REM ffmpeg is fatal for the mux step. Fail here, not after minutes of TTS.
where /q ffmpeg
if not errorlevel 1 goto :ffok
echo       WARNING: ffmpeg is NOT in PATH - video mux will fail at the very end
echo                install:  winget install Gyan.FFmpeg    then open a NEW window
goto :chromium
:ffok
echo       ffmpeg ok

:chromium
venv\Scripts\python -c "from playwright.sync_api import sync_playwright" >nul 2>nul
if errorlevel 1 goto :pwmissing
venv\Scripts\python -m playwright install chromium >> "%LOG%" 2>&1
echo       chromium ok (playwright)
goto :ttsassets
:pwmissing
echo       WARNING: playwright not importable - deck capture disabled
echo                see %LOG%

:ttsassets
REM Supertonic3 TTS models. ~395MB, kept out of git on purpose.
if exist "vendor\chodangi\assets\onnx" goto :ttsok
echo       WARNING: TTS models missing - vendor\chodangi\assets\onnx
echo                copy the assets\ folder from a machine that has it
echo                (video render works only with --no-audio until then)
goto :done
:ttsok
echo       TTS models ok

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
