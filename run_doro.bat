@echo off
REM ============================================================
REM  Doro launcher - double-click to start the desktop pet.
REM
REM  Runs windowless via pythonw (no black console window).
REM  If Doro doesn't appear, run run_doro_debug.bat instead to
REM  see the error message.
REM ============================================================

REM Work from this script's own folder so doro.py and res/ resolve.
cd /d "%~dp0"

REM Launch detached and windowless. "Doro" is just the (hidden) title.
start "Doro" pythonw doro.py %*
