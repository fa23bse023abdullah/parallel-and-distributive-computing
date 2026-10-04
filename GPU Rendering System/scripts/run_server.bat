@echo off
title GPU Offloading - Server Worker Daemon
cd /d "%~dp0\.."
echo =======================================================
echo   STARTING GPU OFFLOADING WORKER DAEMON
echo =======================================================
python -m server.server_daemon --host 0.0.0.0 --port 9850
pause
