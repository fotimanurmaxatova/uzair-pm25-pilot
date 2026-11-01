
@echo off
cd /d "%~dp0.."
if not exist logs mkdir logs
echo [%date% %time%] start >> logs\assessed.log
.venv\Scripts\python.exe -m uzair.cli collect --assessed --scheduled >> logs\assessed.log 2>&1
echo [%date% %time%] exit=%errorlevel% >> logs\assessed.log
