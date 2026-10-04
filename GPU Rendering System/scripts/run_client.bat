@echo off
title GPU Offloading - Client Desktop GUI
cd /d "%~dp0\.."
echo =======================================================
echo   STARTING GPU OFFLOADING CLIENT DESKTOP GUI
echo =======================================================
python -m client.client_app
pause
