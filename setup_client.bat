@echo off
title ShopFlow POS -- 1-Click Client System Setup
color 0b
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ======================================================================
echo          SHOPFLOW POS -- CLIENT SYSTEM INSTALLER & SETUP
echo ======================================================================
echo.
echo Setting up ShopFlow Point of Sale on this system...
echo.

:: 1. Ensure Local AppData Directory exists
set "APP_DATA=%LOCALAPPDATA%\ShopFlowPOS"
if not exist "%APP_DATA%" (
    echo [+] Creating application directory: %APP_DATA%
    mkdir "%APP_DATA%"
)

:: 2. Create Desktop Shortcut via PowerShell
echo [+] Creating Desktop Shortcut...
set "TARGET_EXE=%~dp0dist\ShopFlowPOS.exe"
if not exist "%TARGET_EXE%" set "TARGET_EXE=%~dp0run_pos.bat"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'ShopFlow POS.lnk')); $Shortcut.TargetPath = '%TARGET_EXE%'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.Description = 'ShopFlow POS - Offline Retail Point of Sale'; $Shortcut.Save()"

if %errorlevel% equ 0 (
    echo     [SUCCESS] Desktop Shortcut 'ShopFlow POS' created!
) else (
    echo     [NOTE] Desktop shortcut skipped.
)

echo.
echo ======================================================================
echo                    INITIAL STORE CONFIGURATION
echo ======================================================================
echo.
echo Choose your setup mode:
echo   [1] PITCH / DEMO MODE  -- Load 36 sample products, customers, Khata & sales
echo   [2] LIVE FRESH STORE   -- Start completely clean (0 products, 0 sales)
echo   [3] KEEP CURRENT DATA  -- Launch existing database without changes
echo.
set /p "CHOICE=Enter choice (1, 2, or 3): "

if "%CHOICE%"=="1" (
    echo.
    echo [*] Seeding demo store products and analytics...
    if exist ".venv312\Scripts\python.exe" (
        ".venv312\Scripts\python.exe" seed_demo_store.py
    ) else (
        python seed_demo_store.py
    )
    echo     [SUCCESS] Demo store ready! PIN: 1234 (Admin)
) else if "%CHOICE%"=="2" (
    echo.
    echo [*] Resetting to factory-fresh store...
    if exist ".venv312\Scripts\python.exe" (
        ".venv312\Scripts\python.exe" -c "import reset_store_clean; reset_store_clean.reset_to_clean()"
    ) else (
        python -c "import reset_store_clean; reset_store_clean.reset_to_clean()"
    )
    echo     [SUCCESS] Clean database initialized! PIN: 1234 (Admin)
) else (
    echo.
    echo [*] Keeping existing database intact.
)

echo.
echo ======================================================================
echo                   HARDWARE & ENVIRONMENT READY
echo ======================================================================
echo.
echo Hardware Quick Tips:
echo   * Barcode Scanner: Plug into any USB port (ready automatically).
echo   * Thermal Printer: Connect USB cable and set as Windows default printer.
echo   * Cash Drawer: Connect RJ11 cable to the back of the thermal printer.
echo.
set /p "LAUNCH=Launch ShopFlow POS now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    start "" run_pos.bat
)

echo.
echo Setup complete! You can start ShopFlow POS anytime from your Desktop.
echo.
pause
