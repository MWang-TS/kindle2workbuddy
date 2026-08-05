@echo off
chcp 65001 >nul
echo ============================================
echo   Kindle RNDIS 驱动安装
echo ============================================
echo.
echo 正在安装 RNDIS 驱动 (kindle_rndis.inf)...
echo.
pnputil /add-driver "E:\workbuddy\2026-08-05-10-54-06\kindle-dashboard\kindle_rndis.inf" /install
echo.
echo ============================================
echo 如果上面显示 "Added driver packages: 1" 说明成功
echo 如果显示 "Access is denied" 说明没有管理员权限
echo   请右键此文件 → 以管理员身份运行
echo ============================================
echo.
echo 按任意键退出...
pause >nul
