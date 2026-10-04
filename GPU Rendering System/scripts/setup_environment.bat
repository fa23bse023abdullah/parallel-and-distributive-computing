@echo off
title GPU Offloading - Setup Environment
cd /d "%~dp0\.."
echo =======================================================
echo   INSTALLING DEPENDENCIES & CHECKING PREREQUISITES
echo =======================================================
python -m pip install -r requirements.txt
echo.
echo Verifying system capabilities...
python scripts\verify_system.py
pause
