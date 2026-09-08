@echo off
rem Opens the Sales Margin Control dashboard with its Refresh button working.
rem
rem The button needs something on this machine that can reach Business Central, because
rem the browser cannot: BC is on-prem behind a self-signed certificate, sends no CORS
rem headers, and its credentials must never reach a browser. serve.py is that something.
rem
rem Double-click this file. Leave the window open while you use the dashboard; closing it
rem stops the server and the button stops working (the page still shows its last data).

setlocal
cd /d "%~dp0"

set "PY=C:\Python314\python.exe"
if not exist "%PY%" set "PY=python"

echo Starting the dashboard server...
echo Close this window when you are done.
echo.
"%PY%" serve.py
if errorlevel 1 (
  echo.
  echo The server stopped with an error. The message above says why.
  pause
)
endlocal
