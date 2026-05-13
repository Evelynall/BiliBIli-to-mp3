@echo off
chcp 65001 >nul
title Bilibili to MP3 Tool Launcher

echo ========================================
echo   Bilibili Video to MP3 Converter
echo ========================================
echo.

set "PYTHON_EXE="

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    goto :found
)
if exist "%ProgramFiles%\Python313\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python313\python.exe"
    goto :found
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    goto :found
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python311\python.exe"
    goto :found
)
if exist "%ProgramFiles%\Python310\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python310\python.exe"
    goto :found
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    goto :found
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :found
)

echo [ERROR] Python not found!
echo Please install Python 3.8 or higher from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:found
echo [OK] Found Python: %PYTHON_EXE%

%PYTHON_EXE% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] tkinter module not found!
    echo Please reinstall Python and make sure to install tcl/tk and IDLE.
    pause
    exit /b 1
)
echo [OK] tkinter is available

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found! Audio conversion requires ffmpeg.
    echo Download from: https://ffmpeg.org/download.html
    echo.
) else (
    echo [OK] ffmpeg is available
)

echo.
echo [*] Installing dependencies...
%PYTHON_EXE% -m pip install --user -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo [OK] Dependencies ready
echo.

echo [*] Starting application...
echo.
%PYTHON_EXE% "%~dp0bilibili_to_mp3.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
