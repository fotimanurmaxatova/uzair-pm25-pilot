@echo off
cd /d C:\Users\admin\UzAir_projects\uzair-pm25-pilot
echo [%date% %time%] start >> logs\collect.log
.venv\Scripts\python.exe -m uzair.cli collect --scheduled >> logs\collect.log 2>&1
echo [%date% %time%] done >> logs\collect.log