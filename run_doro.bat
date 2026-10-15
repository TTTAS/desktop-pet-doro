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

REM Optional feature sets to install. factory = asset factory - OpenCV, Pillow, numpy.
set "DORO_EXTRAS=web,automation,a11y,factory"
REM Installed after the above but allowed to fail: factory-ai = AI background
REM removal - rembg plus onnxruntime, a large download. Doro still starts
REM without it and the asset factory falls back to color removal.
set "DORO_OPTIONAL=factory-ai"

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

REM 3) install deps on first run, OR whenever pyproject.toml, DORO_EXTRAS or DORO_OPTIONAL changed.
REM    The marker stores the hash of pyproject.toml plus the extras list.
REM    When either changes later - e.g. a new package like websockets, or a
REM    new extra like factory - it no longer matches and we reinstall, so
REM    old venvs pick up the new packages instead of silently missing them.
set "PYPROJECT_HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "pyproject.toml" SHA256') do if not defined PYPROJECT_HASH set "PYPROJECT_HASH=%%H"

set "SAVED_HASH="
if exist ".venv\.doro_setup_done" set /p SAVED_HASH=<".venv\.doro_setup_done"

if not defined PYPROJECT_HASH goto do_setup
if /I "%SAVED_HASH%"=="%PYPROJECT_HASH% %DORO_EXTRAS% %DORO_OPTIONAL%" goto run

:do_setup
echo [setup] installing dependencies, first time takes a few minutes ...
python -m pip install --upgrade pip
python -m pip install -e ".[%DORO_EXTRAS%]"
if errorlevel 1 goto err_pip

echo [setup] downloading Playwright browser Chromium ...
python -m playwright install chromium
if errorlevel 1 goto err_pw

echo [setup] installing AI background removal, optional and large ...
python -m pip install -e ".[%DORO_OPTIONAL%]"
if errorlevel 1 goto warn_ai
goto setup_done

:warn_ai
echo [warn] AI background removal could not be installed. Doro still runs;
echo [warn] the asset factory can use color removal. To retry later run:
echo [warn]   .venv\Scripts\python -m pip install -e ".[%DORO_OPTIONAL%]"

:setup_done
echo %PYPROJECT_HASH% %DORO_EXTRAS% %DORO_OPTIONAL%> ".venv\.doro_setup_done"
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
