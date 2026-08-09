@echo off
setlocal
cd /d "%~dp0"

set "MSP_PYTHON=.venv\Scripts\python.exe"
if not exist "%MSP_PYTHON%" (
    where py >nul 2>nul || (
        echo Python 3.11 or newer was not found. Install Python from python.org.
        exit /b 1
    )
    py -3.11 -m venv .venv || exit /b 1
)

"%MSP_PYTHON%" -m pip install --upgrade pip || exit /b 1
"%MSP_PYTHON%" -m pip install -e . pyinstaller || exit /b 1
"%MSP_PYTHON%" tools\run_tests.py all -q || exit /b 1

"%MSP_PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onedir ^
    --name MercurySkyPulse ^
    --paths src ^
    apps\desktop\main.py || exit /b 1

echo.
echo Build complete: dist\MercurySkyPulse\MercurySkyPulse.exe
echo Copy the entire dist\MercurySkyPulse directory when testing another PC.
endlocal
