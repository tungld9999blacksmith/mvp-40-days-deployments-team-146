@echo off
REM Cross-platform Python launcher for AI log hooks (Windows cmd.exe).
REM Prefer the repository venv; execute probes to skip Windows Store aliases.
setlocal
cd /d "%~dp0.." || exit /b 1

if not exist ".venv\Scripts\python.exe" goto try_py
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  ".venv\Scripts\python.exe" %*
  goto finished
)

:try_py
py -3 -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 %*
  goto finished
)

python -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  python %*
  goto finished
)

python3 -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 %*
  goto finished
)

echo [ai-log] No working Python found. Create the repository .venv or install Python. 1>&2
exit /b 1

:finished
exit /b %ERRORLEVEL%
