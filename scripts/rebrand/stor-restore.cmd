@echo off
REM Restore Prostor rebrand after `prostor update`
REM Usage: stor-restore.cmd

cd /d "%~dp0\.."
python scripts\rebrand\restore_prostor.py
pause
