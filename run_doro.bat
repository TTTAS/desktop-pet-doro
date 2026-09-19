@echo off
setlocal
REM ============================================================
REM  run_doro.bat  -  run doro inside a local venv
REM  ASCII-only, and NO parentheses inside if-blocks
REM  (unescaped ")" inside a block breaks cmd parsing).
REM
REM  Usage:
REM    double-click, or run:  run_doro.bat
REM    with web-operation debug output:  run_doro.bat debug
REM
REM  First run installs everything, so it takes a few minutes.
REM  Later runs are fast.
REM ============================================================

cd /d "%~dp0"

if /I "%~1"=="debug" set "DORO_WEB_DEBUG=1"
if defined DORO_WEB_DEBUG echo [debug] web-operation debug output is ON

REM 1) create venv if missing
if not exist ".venv\Scripts\python.exe" goto make_venv
goto have_venv

:make_venv
echo [setup] creating virtual environment .venv ...
python -m venv .venv
if errorlevel 1 goto err_venv

:have_venv
REM 2) activate venv
call ".venv\Scripts\activate.bat"

REM 3) install deps on first run, OR whenever pyproject.toml changed.
REM    The marker stores the hash of pyproject.toml. When the dependency
REM    list changes later (e.g. a new package like websockets is added),
REM    the hash no longer matches and we reinstall, so old venvs pick up
REM    the new packages instead of silently missing them.
set "PYPROJECT_HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "pyproject.toml" SHA256') do if not defined PYPROJECT_HASH set "PYPROJECT_HASH=%%H"

set "SAVED_HASH="
if exist ".venv\.doro_setup_done" set /p SAVED_HASH=<".venv\.doro_setup_done"

if not defined PYPROJECT_HASH goto do_setup
if /I "%SAVED_HASH%"=="%PYPROJECT_HASH%" goto run

:do_setup
echo [setup] installing dependencies, first time takes a few minutes ...
python -m pip install --upgrade pip
python -m pip install -e ".[web,automation,a11y]"
if errorlevel 1 goto err_pip

echo [setup] downloading Playwright browser Chromium ...
python -m playwright install chromium
if errorlevel 1 goto err_pw

echo %PYPROJECT_HASH%> ".venv\.doro_setup_done"
echo [setup] done.

:run
echo [run] starting doro ...
python doro.py
echo.
echo [exit] doro closed.
pause
goto :eof

:err_venv
echo [ERROR] failed to create venv. Install Python 3.10+ and put it on PATH.
pause
goto :eof

:err_pip
echo [ERROR] pip install failed, see messages above.
pause
goto :eof

:err_pw
echo [ERROR] playwright install failed, see messages above.
pause
goto :eof
