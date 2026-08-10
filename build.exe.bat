@echo off
setlocal
cd /d "%~dp0"

echo MercurySkyPulse Windows test build
echo Repository: %CD%
echo.

set "MSP_MERCURY_VERSION=1.9.11"
set "MSP_MERCURY_ARCHIVE_NAME=mercury-1.9.11-w64-f5c8a2f0.zip"
set "MSP_MERCURY_ARCHIVE_SHA256=a88c7739428e7afe864791a964d5f8eaa0fc73d6d0a60c016a6df0a5e30a9e78"
set "MSP_MERCURY_URL=https://github.com/Rhizomatica/mercury/releases/download/v1.9.11/mercury-1.9.11-w64-f5c8a2f0.zip"
set "MSP_MERCURY_LICENSE_URL=https://raw.githubusercontent.com/Rhizomatica/mercury/v1.9.11/LICENSE"
set "MSP_MERCURY_LICENSE_SHA256=3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
set "MSP_MERCURY_CACHE=%TEMP%\MercurySkyPulse-build-cache\mercury-%MSP_MERCURY_VERSION%"
set "MSP_MERCURY_ARCHIVE=%MSP_MERCURY_CACHE%\%MSP_MERCURY_ARCHIVE_NAME%"
set "MSP_MERCURY_LICENSE=%MSP_MERCURY_CACHE%\LICENSE"
set "MSP_MERCURY_RUNTIME=%MSP_MERCURY_CACHE%\runtime\mercury-%MSP_MERCURY_VERSION%"

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

call :prepare_mercury
if errorlevel 1 (
    echo ERROR: The pinned Mercury runtime could not be downloaded or verified.
    echo Check the network connection and the detailed message above.
    goto failed
)
echo Mercury runtime: %MSP_MERCURY_RUNTIME%

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
    --icon assets\icons\mercuryskypulse.ico ^
    --add-data "assets\icons\mercuryskypulse.png;assets\icons" ^
    --paths src ^
    apps\desktop\main.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed to create the executable.
    goto failed
)

echo Adding Mercury to the test package...
xcopy /E /I /Y "%MSP_MERCURY_RUNTIME%\*" "dist\MercurySkyPulse\mercury" >nul
if errorlevel 1 (
    echo ERROR: The Mercury runtime could not be copied into the test package.
    goto failed
)
copy /Y "%MSP_MERCURY_LICENSE%" "dist\MercurySkyPulse\mercury\LICENSE" >nul
if errorlevel 1 (
    echo ERROR: The Mercury license could not be copied into the test package.
    goto failed
)
(
    echo Mercury %MSP_MERCURY_VERSION%
    echo Corresponding source: https://github.com/Rhizomatica/mercury/tree/v%MSP_MERCURY_VERSION%
    echo License: GNU GPL-3.0; see LICENSE in this directory.
) > "dist\MercurySkyPulse\mercury\SOURCE.txt"

echo.
echo Build complete: dist\MercurySkyPulse\MercurySkyPulse.exe
echo Mercury included: dist\MercurySkyPulse\mercury\mercury.exe
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

:prepare_mercury
if not exist "%MSP_MERCURY_CACHE%" mkdir "%MSP_MERCURY_CACHE%"
if errorlevel 1 (
    echo ERROR: Could not create Mercury download cache: %MSP_MERCURY_CACHE%
    exit /b 1
)
if not exist "%MSP_MERCURY_ARCHIVE%" (
    echo Downloading pinned Mercury %MSP_MERCURY_VERSION% runtime...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri $env:MSP_MERCURY_URL -OutFile $env:MSP_MERCURY_ARCHIVE"
    if errorlevel 1 (
        echo ERROR: Mercury runtime download failed.
        exit /b 1
    )
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "if ((Get-FileHash -LiteralPath $env:MSP_MERCURY_ARCHIVE -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:MSP_MERCURY_ARCHIVE_SHA256) { exit 1 }"
if errorlevel 1 (
    echo ERROR: Mercury runtime SHA-256 verification failed.
    del /Q "%MSP_MERCURY_ARCHIVE%" >nul 2>nul
    exit /b 1
)
if not exist "%MSP_MERCURY_LICENSE%" (
    echo Downloading Mercury GPL license...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri $env:MSP_MERCURY_LICENSE_URL -OutFile $env:MSP_MERCURY_LICENSE"
    if errorlevel 1 (
        echo ERROR: Mercury license download failed.
        exit /b 1
    )
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "if ((Get-FileHash -LiteralPath $env:MSP_MERCURY_LICENSE -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:MSP_MERCURY_LICENSE_SHA256) { exit 1 }"
if errorlevel 1 (
    echo ERROR: Mercury license SHA-256 verification failed.
    del /Q "%MSP_MERCURY_LICENSE%" >nul 2>nul
    exit /b 1
)
if not exist "%MSP_MERCURY_RUNTIME%\mercury.exe" (
    echo Extracting Mercury runtime...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$destination=Join-Path $env:MSP_MERCURY_CACHE 'runtime'; if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }; Expand-Archive -LiteralPath $env:MSP_MERCURY_ARCHIVE -DestinationPath $destination -Force"
    if errorlevel 1 (
        echo ERROR: Mercury runtime extraction failed.
        exit /b 1
    )
)
if not exist "%MSP_MERCURY_RUNTIME%\mercury.exe" (
    echo ERROR: Verified Mercury archive did not contain mercury.exe.
    exit /b 1
)
exit /b 0

:failed
echo.
echo Build failed. Review the ERROR message above.
echo Press any key to close this window.
pause >nul
exit /b 1
