@echo off
title Articul8 Bivia Image Sorter - Desktop Batch Sort
echo =====================================================================
echo  Articul8 Bivia - Automated Desktop Image Sorter
echo =====================================================================
echo  Input (Raw Mixed Images)  : C:\Users\Kiruthik Kumar\Desktop\Raw_Images
echo  Output (Sorted Subfolders): C:\Users\Kiruthik Kumar\Desktop\Sorted_Images
echo =====================================================================
cd /d "%~dp0"
python sorter.py --input "C:\Users\Kiruthik Kumar\Desktop\Raw_Images" --output "C:\Users\Kiruthik Kumar\Desktop\Sorted_Images" --preset industrial_safety
pause
