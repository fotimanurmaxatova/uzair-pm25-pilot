@echo off
cd /d "%~dp0.."
if not exist logs mkdir logs
echo [%date% %time%] start >> logs\collect.log
.venv\Scripts\python.exe -m uzair.cli collect --scheduled >> logs\collect.log 2>&1
echo [%date% %time%] exit=%errorlevel% >> logs\collect.log
