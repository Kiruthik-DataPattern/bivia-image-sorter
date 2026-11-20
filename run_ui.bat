@echo off
title System One Image Sorter UI
cd /d "%~dp0"
echo Starting System One Image Sorter UI Server...
start "" http://localhost:5050
python app.py
pause
