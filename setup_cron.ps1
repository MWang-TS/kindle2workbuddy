# WorkBuddy Kindle Dashboard - 创建 Windows 定时任务
# 每 3 分钟自动刷新 Kindle 屏幕
#
# 用法（管理员权限 PowerShell）：
#   powershell -ExecutionPolicy Bypass -File setup_cron.ps1

$TaskName = "WorkBuddy Kindle Dashboard Refresh"
# Python 解释器路径：默认用 PATH 里的 python，也可改成绝对路径（如虚拟环境内的 python.exe）
$PythonPath = "python.exe"
$ScriptPath = Join-Path $PSScriptRoot "refresh.py"

# 检查 python 是否存在
$PythonCmd = Get-Command $PythonPath -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Error "找不到 Python，请将 `$PythonPath 改为你的 python.exe 绝对路径"
    exit 1
}
$PythonPath = $PythonCmd.Source

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建新任务
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $ScriptPath
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date)).Repetition
$Trigger.Repetition.Interval = "PT3M"        # 每 3 分钟
$Trigger.Repetition.Duration = "P1D"         # 持续 1 天后会因下一次 AtLogOn 重新触发
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "每 3 分钟生成并推送 dashboard.png 到 Kindle，刷新 e-ink 屏显示" `
    -User "$env:USERNAME" `
    -RunLevel Highest

Write-Host ""
Write-Host "✅ 定时任务已创建: $TaskName" -ForegroundColor Green
Write-Host "   触发器: 登录时启动 + 每 3 分钟重复" -ForegroundColor Gray
Write-Host "   脚本: $ScriptPath" -ForegroundColor Gray
Write-Host ""
Write-Host "管理任务命令：" -ForegroundColor Cyan
Write-Host "  查看: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  立即运行: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  删除: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
