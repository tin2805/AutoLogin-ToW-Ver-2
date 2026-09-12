@echo off
title Tales of Wind - Auto Login Tool
cd /d "%~dp0"

set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 set "PY_CMD=py"
    )
)

"%PY_CMD%" app_ui.py
if errorlevel 1 (
    echo.
    echo Co loi xay ra khi chay chuong trinh!
    pause
)

