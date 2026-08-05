' Kindle Dashboard Daemon Launcher (silent / no window)
' 使用前请将 pythonw.exe 路径改为你自己的 Python 解释器路径
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw.exe """ & Replace(WScript.ScriptFullName, "daemon.vbs", "daemon.py") & """", 0, False
Set WshShell = Nothing