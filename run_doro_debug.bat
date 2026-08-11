@echo off
REM ============================================================
REM  Doro launcher (debug) - keeps a console open so you can
REM  read any startup error. Use this if run_doro.bat silently
REM  does nothing.
REM ============================================================

cd /d "%~dp0"

echo Starting Doro (debug)...
echo Working folder: %cd%
echo.

python doro.py %*

echo.
echo ------------------------------------------------------------
echo Doro exited (see any error above). Press any key to close.
pause >nul
