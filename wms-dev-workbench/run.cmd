@echo off
rem Start the WMS Dev Workbench (needs a Python with flask, sqlalchemy, pyodbc on PATH).
cd /d "%~dp0"
python app.py
