@echo off
rem Start the workbench hidden in the background (no console window), then open the browser.
rem Logs: server.log / server.err.log in this folder. Stop with stop.cmd.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList 'app.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%~dp0server.log' -RedirectStandardError '%~dp0server.err.log'"
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:8765
