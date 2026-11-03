@echo off
rem Stops the X Education API, website and CRM started by start-all.bat (whatever listens on ports 8000, 5173 and
rem 5174), with the windows they run in. Data is kept: the next start-all.bat continues where this one stopped.
rem "stop-all.bat quiet" stops without messages or a pause (start-all.bat uses it to clear an earlier run).

setlocal EnableExtensions
set "QUIET=%~1"
set "STOPPED=0"
for %%P in (8000 5173 5174) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    taskkill /PID %%I /T /F >nul 2>nul
    set "STOPPED=1"
  )
)
taskkill /FI "WINDOWTITLE eq X Education API*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq X Education website*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq X Education CRM*" /T /F >nul 2>nul
if /i "%QUIET%"=="quiet" exit /b 0
if "%STOPPED%"=="1" (
  echo The API, the website and the CRM are stopped. Your data is kept in backend\data.
) else (
  echo Nothing was running.
)
pause
