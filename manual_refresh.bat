@echo off
chcp 65001 >nul 2>nul
echo.
echo ============================================
echo   WorkBuddy Kindle Dashboard Refresh
echo ============================================
echo.
cd /d "E:\workbuddy\2026-08-05-10-54-06\kindle-dashboard"
"C:\Users\wangm\.workbuddy\binaries\python\envs\default\Scripts\python.exe" refresh.py
echo.
echo ============================================
echo   Done - Press any key to close
echo ============================================
pause >nul 2>nul
