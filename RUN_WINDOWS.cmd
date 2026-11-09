@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0bootstrap.py" %*
) else (
  python "%~dp0bootstrap.py" %*
)
if errorlevel 1 pause
endlocal
