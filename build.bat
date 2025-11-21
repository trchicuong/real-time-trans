@echo off
echo Building Real-time Screen Translator...
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

echo.
echo Choose build type:
echo 1. Release (no console window)
echo 2. Debug (with console window to see errors)
set /p build_type="Enter choice (1 or 2): "

if "%build_type%"=="2" (
    echo.
    echo Creating DEBUG executable (with console)...
    pyinstaller --onedir --console --name "RealTimeScreenTranslator-DEBUG" --icon=NONE translator.py
) else (
    echo.
    echo Creating RELEASE executable (no console)...
    if exist build.spec (
        pyinstaller build.spec
    ) else (
        pyinstaller --onedir --windowed --name "RealTimeScreenTranslator" --icon=NONE translator.py
    )
)

echo.
echo Build complete! Check the 'dist' folder for the executable.
echo.
echo If the exe doesn't work, try the DEBUG version to see error messages.
pause
