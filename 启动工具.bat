@echo off
chcp 65001 >nul
title Music Tools Launcher

set PYTHON_EXE=

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
    goto found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
    goto found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
    goto found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe
    goto found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python39\python.exe
    goto found
)
if exist "%ProgramFiles%\Python313\python.exe" (
    set PYTHON_EXE=%ProgramFiles%\Python313\python.exe
    goto found
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set PYTHON_EXE=%ProgramFiles%\Python312\python.exe
    goto found
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set PYTHON_EXE=%ProgramFiles%\Python311\python.exe
    goto found
)
if exist "%ProgramFiles%\Python310\python.exe" (
    set PYTHON_EXE=%ProgramFiles%\Python310\python.exe
    goto found
)

where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=py
    goto found
)

where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=python
    goto found
)

echo [ERROR] Python not found!
pause
exit /b 1

:found
echo [OK] Found Python: %PYTHON_EXE%

echo.
echo ========================================
echo     Music Tools Launcher
echo ========================================
echo.
echo  1. Bilibili to MP3
echo  2. MP3 Metadata Editor
echo  3. Exit
echo.

set /p choice=Select (1-3): 

if "%choice%"=="1" goto run_bilibili
if "%choice%"=="2" goto run_editor
if "%choice%"=="3" goto exit_script

echo [ERROR] Invalid choice!
goto ask_choice

:ask_choice
set /p choice=Select (1-3): 
if "%choice%"=="1" goto run_bilibili
if "%choice%"=="2" goto run_editor
if "%choice%"=="3" goto exit_script
echo [ERROR] Invalid choice!
goto ask_choice

:run_bilibili
echo [*] Starting Bilibili to MP3...
start "" "%PYTHON_EXE%" "%~dp0bilibili_to_mp3.py"
goto end

:run_editor
echo [*] Starting MP3 Metadata Editor...
start "" "%PYTHON_EXE%" "%~dp0mp3_metadata_editor.py"
goto end

:exit_script
exit /b 0

:end
