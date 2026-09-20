@echo off
title Cai Dat Thu Vien - Tales of Wind Auto Login Tool
cd /d "%~dp0"

echo ============================================================
echo   TALES OF WIND AUTO LOGIN - CAI DAT THU VIEN
echo ============================================================
echo.

set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=py"
        ) else (
            echo [X] KHONG TIM THAY PYTHON TREN MAY TINH CUA BAN!
            echo Vui long cai dat Python tu https://www.python.org/
            echo Nho tick chon Add Python to PATH khi cai dat.
            echo.
            pause
            exit /b 1
        )
    )
)

echo [*] Python executable: %PY_CMD%
echo.

"%PY_CMD%" install_requirements.py

if errorlevel 1 (
    echo.
    echo [X] Co loi xay ra trong qua trinh cai dat. Vui long kiem tra lai.
) else (
    echo.
    echo [OK] Hoan tat! Ban co the chay run_tool.bat de mo tool.
)

echo.
pause
