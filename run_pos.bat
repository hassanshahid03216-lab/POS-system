@echo off
title ShopFlow POS Launcher
setlocal EnableDelayedExpansion

cd /d "%~dp0"

:: Check if standalone executable exists
if exist "dist\ShopFlowPOS.exe" (
    start "" "dist\ShopFlowPOS.exe"
    exit /b 0
)

if exist "dist\ShopFlowPOS\ShopFlowPOS.exe" (
    start "" "dist\ShopFlowPOS\ShopFlowPOS.exe"
    exit /b 0
)

if exist "ShopFlowPOS.exe" (
    start "" "ShopFlowPOS.exe"
    exit /b 0
)

:: Otherwise check Python virtual environment
if exist ".venv312\Scripts\pythonw.exe" (
    start "" ".venv312\Scripts\pythonw.exe" main.py
    exit /b 0
)

if exist ".venv312\Scripts\python.exe" (
    start "" ".venv312\Scripts\python.exe" main.py
    exit /b 0
)

:: Fallback to system python
python -V >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw main.py
    exit /b 0
)

echo [ERROR] Could not locate ShopFlowPOS.exe or a Python installation!
echo Please run setup_client.bat first to configure your system.
pause
