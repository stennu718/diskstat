$pyinstaller = Join-Path $env:APPDATA "Python\Python314\Scripts\pyinstaller.exe"
cd $PSScriptRoot
& $pyinstaller --onefile --console --clean --name diskstat --add-data "template.html;." diskstat.py
