@echo off
rem X Education CRM: install what is missing, prepare the data, and start the API, the website and the CRM.
rem Double-click this file, or run it from a Command Prompt in the project folder. stop-all.bat stops everything.
rem The first start takes about 15 minutes (packages, models, the six-month simulated history); later starts take
rem seconds. Needs Python 3.10 or newer (3.12 recommended) and Node.js 20.19 or newer.

setlocal EnableExtensions
title X Education start-up
cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHONUTF8=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo.
echo  X Education CRM
echo  ===============
echo.

rem ---- Python 3.10 or newer
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=py -3.12"
)
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
  )
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
  )
)
if not defined PY (
  echo  Python 3.10 or newer was not found. Install Python 3.12 from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" in the installer, then run this file again.
  goto :fail
)

rem ---- Node.js 20.19 or newer
where node >nul 2>nul
if errorlevel 1 (
  echo  Node.js was not found. Install the LTS version from https://nodejs.org/ and run this file again.
  goto :fail
)
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>20||(a===20&&b>=19)?0:1)"
if errorlevel 1 (
  echo  Node.js 20.19 or newer is needed. Install the LTS version from https://nodejs.org/
  goto :fail
)

rem ---- the API's Python environment (backend\.venv), packages installed when requirements.txt changes
set "VPY=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo  [1/5] Creating the Python environment in backend\.venv ...
  %PY% -m venv "%ROOT%\backend\.venv"
  if errorlevel 1 goto :fail
) else (
  echo  [1/5] Python environment found.
)
certutil -hashfile "%ROOT%\backend\requirements.txt" SHA256 | findstr /v ":" > "%ROOT%\backend\.venv\requirements.new"
fc /b "%ROOT%\backend\.venv\requirements.new" "%ROOT%\backend\.venv\requirements.sha" >nul 2>nul
if errorlevel 1 (
  echo  [2/5] Installing the API's packages - a few minutes the first time ...
  "%VPY%" -m pip install --quiet --upgrade pip
  "%VPY%" -m pip install -r "%ROOT%\backend\requirements.txt"
  if errorlevel 1 goto :fail
  move /y "%ROOT%\backend\.venv\requirements.new" "%ROOT%\backend\.venv\requirements.sha" >nul
) else (
  del "%ROOT%\backend\.venv\requirements.new" >nul 2>nul
  echo  [2/5] API packages are up to date.
)

rem ---- settings file (optional values only: email, Gemini; see backend\.env.example)
if not exist "%ROOT%\backend\.env" copy "%ROOT%\backend\.env.example" "%ROOT%\backend\.env" >nul

rem ---- database, starting models and the simulated starting history (only what is missing)
echo  [3/5] Preparing the database and the models ...
pushd "%ROOT%\backend"
"%VPY%" -m app.cli bootstrap
if errorlevel 1 (
  popd
  goto :fail
)
popd

rem ---- the website's and the CRM's packages, installed when package-lock.json changes
certutil -hashfile "%ROOT%\frontend\package-lock.json" SHA256 | findstr /v ":" > "%ROOT%\frontend\lock.new"
fc /b "%ROOT%\frontend\lock.new" "%ROOT%\frontend\node_modules\.lock.sha" >nul 2>nul
if errorlevel 1 (
  echo  [4/5] Installing the website's and the CRM's packages - a few minutes the first time ...
  pushd "%ROOT%\frontend"
  call npm ci --no-audit --no-fund
  if errorlevel 1 (
    popd
    goto :fail
  )
  popd
  move /y "%ROOT%\frontend\lock.new" "%ROOT%\frontend\node_modules\.lock.sha" >nul
) else (
  del "%ROOT%\frontend\lock.new" >nul 2>nul
  echo  [4/5] Website and CRM packages are up to date.
)

rem ---- start the three servers, each in its own window
echo  [5/5] Starting the API, the website and the CRM ...
call "%ROOT%\stop-all.bat" quiet
start "X Education API" /d "%ROOT%\backend" cmd /k ""%VPY%" -m app.cli serve"
start "X Education website" /d "%ROOT%\frontend" cmd /k "npm run dev -w web"
start "X Education CRM" /d "%ROOT%\frontend" cmd /k "npm run dev -w crm"

set /a TRIES=0
:wait
set /a TRIES+=1
where curl >nul 2>nul
if not errorlevel 1 (
  curl -sf http://127.0.0.1:8000/api/health >nul 2>nul
) else (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
)
if not errorlevel 1 goto :up
if %TRIES% geq 60 (
  echo  The API did not answer within two minutes. Look at the "X Education API" window for the reason.
  goto :fail
)
timeout /t 2 /nobreak >nul
goto :wait

:up
timeout /t 3 /nobreak >nul
start "" http://localhost:5173
start "" http://localhost:5174
echo.
echo  Running:
echo    Website (learners)   http://localhost:5173
echo    CRM (the team)       http://localhost:5174
echo    API documentation    http://127.0.0.1:8000/api/docs
echo.
if exist "%ROOT%\backend\data\initial-admin-password.txt" (
  echo  First sign-in to the CRM - you choose your own password straight after:
  findstr /b /c:"   email " /c:"   password " "%ROOT%\backend\data\initial-admin-password.txt"
  echo.
)
echo  Without email set up in backend\.env, sign-up codes appear in the "X Education API" window.
echo  To stop everything, run stop-all.bat.
echo.
pause
exit /b 0

:fail
echo.
echo  Start-up stopped. Fix the problem above and run start-all.bat again.
pause
exit /b 1
