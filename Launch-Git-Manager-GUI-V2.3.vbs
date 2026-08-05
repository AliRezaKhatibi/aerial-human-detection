Option Explicit

Dim shell, fso, folder, scriptPath, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = folder & "\aerial-git-manager-gui-v2.3-portable.ps1"

If Not fso.FileExists(scriptPath) Then
    MsgBox "The GUI PowerShell file was not found:" & vbCrLf & scriptPath, 16, "Git Manager GUI V2.3"
    WScript.Quit 1
End If

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File """ & scriptPath & """"
shell.Run command, 0, False
