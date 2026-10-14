@echo off
echo ============================================
echo   Warframe Farm Tracker - building .exe
echo ============================================
echo.

py -m pip install --upgrade pip >nul 2>&1
echo Installing dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Is Python installed and added to PATH?
    pause
    exit /b 1
)

echo.
echo Building FarmTracker.exe (this can take a minute)...
py -m PyInstaller --onefile --windowed --name "FarmTracker" --collect-all customtkinter --collect-all darkdetect --add-data "tessdata;tessdata" main.py
if errorlevel 1 (
    echo.
    echo ERROR: build failed, see the messages above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done! Your exe is in the "dist" folder:
echo   %~dp0dist\FarmTracker.exe
echo ============================================
pause
