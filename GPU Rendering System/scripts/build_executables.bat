@echo off
title Build Standalone Executables (.exe)
cd /d "%~dp0\.."
echo ================================================================
echo   BUILDING STANDALONE EXECUTABLES (.EXE) FOR CLIENT AND SERVER
echo ================================================================

echo.
echo [1/4] Ensuring PyInstaller is installed...
python -m pip install pyinstaller --quiet

echo.
echo [2/4] Building GPU Server Daemon Executable...
python -m PyInstaller --clean -y --paths . --name GPU_Server_Daemon_Standalone --onefile server/server_daemon.py
python -m PyInstaller --clean -y --paths . --name GPU_Server_Daemon --onedir server/server_daemon.py

echo.
echo [3/4] Building GPU Client Studio Desktop GUI Executable...
python -m PyInstaller --clean -y --paths . --collect-all customtkinter --noconsole --name GPU_Client_Studio_Standalone --onefile client/client_app.py
python -m PyInstaller --clean -y --paths . --collect-all customtkinter --noconsole --name GPU_Client_Studio --onedir client/client_app.py

echo.
echo [4/4] Build complete! Executables available in:
echo   - dist\GPU_Server_Daemon_Standalone.exe (Single-file Server Daemon)
echo   - dist\GPU_Client_Studio_Standalone.exe (Single-file Client GUI)
echo   - dist\GPU_Server_Daemon\ (Folder distribution)
echo   - dist\GPU_Client_Studio\ (Folder distribution)
echo ================================================================
pause
