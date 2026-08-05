' Kindle Dashboard Daemon Launcher (silent / no window)
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "C:\Users\wangm\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe """ & Replace(WScript.ScriptFullName, "daemon.vbs", "daemon.py") & """", 0, False
Set WshShell = Nothing