@echo off
rem Stop whatever is listening on the workbench port.
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($c) { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; 'stopped PID ' + $_.OwningProcess } } else { 'nothing listening on 8765' }"
pause
