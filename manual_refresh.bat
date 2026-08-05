@echo off
chcp 65001 >nul 2>nul
echo.
echo ============================================
echo   WorkBuddy Kindle Dashboard Refresh
echo ============================================
echo.
cd /d "%~dp0"
python refresh.py
echo.
echo ============================================
echo   Done - Press any key to close
echo ============================================
pause >nul 2>nul
