@echo off
cd /d "%~dp0"
py main.py
if errorlevel 1 pause
