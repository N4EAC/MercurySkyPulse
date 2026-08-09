@echo off
setlocal
cd /d "%~dp0"

echo MercurySkyPulse Windows test build
echo Repository: %CD%
echo.

set "MSP_PYTHON=.venv\Scripts\python.exe"
if exist "%MSP_PYTHON%" goto verify_venv

call :find_python
if errorlevel 1 (
    echo ERROR: Python 3.11 or newer was not found.
    echo Install Python from https://www.python.org/downloads/windows/
    goto failed
)

echo Creating the virtual environment...
%MSP_BOOTSTRAP% -m venv .venv
if errorlevel 1 (
    echo ERROR: Could not create .venv with %MSP_BOOTSTRAP%.
    goto failed
)

:verify_venv
"%MSP_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo ERROR: .venv must use Python 3.11 or newer.
    echo Delete .venv and run this builder again to recreate it.
    goto failed
)

"%MSP_PYTHON%" --version
echo Updating pip...
"%MSP_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip could not be updated.
    goto failed
)

echo Installing MercurySkyPulse and PyInstaller...
"%MSP_PYTHON%" -m pip install -e . pyinstaller
if errorlevel 1 (
    echo ERROR: Project dependencies or PyInstaller could not be installed.
    goto failed
)

echo Running the aggregate test suite...
"%MSP_PYTHON%" tools\run_tests.py all -q
if errorlevel 1 (
    echo ERROR: Automated tests failed; the executable was not built.
    goto failed
)

echo Building MercurySkyPulse.exe...
"%MSP_PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onedir ^
    --name MercurySkyPulse ^
    --paths src ^
    apps\desktop\main.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed to create the executable.
    goto failed
)

echo.
echo Build complete: dist\MercurySkyPulse\MercurySkyPulse.exe
echo Copy the entire dist\MercurySkyPulse directory when testing another PC.
exit /b 0

:find_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "MSP_BOOTSTRAP=py -3"
        exit /b 0
    )
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "MSP_BOOTSTRAP=python"
        exit /b 0
    )
)
exit /b 1

:failed
echo.
echo Build failed. Review the ERROR message above.
echo Press any key to close this window.
pause >nul
exit /b 1
