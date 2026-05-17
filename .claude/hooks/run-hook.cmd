@echo off
setlocal
REM Windows hook entry wrapper.
REM Routes all hook commands to hook_entry.py.

if "%~1"=="" (
    echo run-hook.cmd: missing hook command >&2
    exit /b 1
)

set "HOOK_DIR=%~dp0"
set "ENTRY=%HOOK_DIR%hook_entry.py"

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 "%ENTRY%" %*
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%ENTRY%" %*
    exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python3 "%ENTRY%" %*
    exit /b %ERRORLEVEL%
)

if /I "%~1"=="feedback-memory" (
    echo python is required >&2
    exit /b 1
)

exit /b 0
