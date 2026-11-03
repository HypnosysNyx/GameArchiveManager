@echo off
cd /d "%~dp0"
start "" "%LocalAppData%\Programs\Python\Python313\pythonw.exe" "%~dp0gui\app.py"
