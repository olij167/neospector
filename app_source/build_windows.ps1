$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path; Set-Location $Root
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Version = (& $Python -c 'import ast,pathlib; t=ast.parse(pathlib.Path("omne_sequencer.py").read_text(encoding="utf-8")); print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="VERSION" for x in n.targets)))')
$Arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString(); if ($Arch -notin @("X64","Arm64")) { throw "Unsupported Windows architecture: $Arch" }
$ArchLabel = if ($Arch -eq "Arm64") { "arm64" } else { "x64" }; $AppName="OmN-e Sequencer"
$Ffmpeg=(Get-Command ffmpeg.exe -ErrorAction Stop).Source; $Ffprobe=(Get-Command ffprobe.exe -ErrorAction Stop).Source; $Ffplay=(Get-Command ffplay.exe -ErrorAction Stop).Source
& $Python -m pip install --upgrade pip; & $Python -m pip install 'pyinstaller>=6.22,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3'
if ($LASTEXITCODE -ne 0) { throw "Build dependencies could not be installed" }
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build,dist,dist-installer
& $Python -m PyInstaller --noconfirm --clean --windowed --hidden-import=PIL._tkinter_finder --name $AppName --add-binary "$Ffmpeg;tools" --add-binary "$Ffprobe;tools" --add-binary "$Ffplay;tools" --add-data ".\ui_profile.json;." --add-data "..\examples;examples" .\omne_sequencer.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
$Dist=Join-Path $Root "dist\$AppName"; $Zip=Join-Path $Root "OmN-e_Sequencer_v${Version}_Windows_${ArchLabel}_Portable.zip"; Compress-Archive -Path "$Dist\*" -DestinationPath $Zip -CompressionLevel Optimal -Force
(Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()+"  "+(Split-Path -Leaf $Zip) | Set-Content -Encoding ascii "${Zip}.sha256"
$IsccCandidates=@("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe","$env:ProgramFiles\Inno Setup 6\ISCC.exe");$Iscc=$IsccCandidates|Where-Object{$_ -and (Test-Path $_)}|Select-Object -First 1
if (-not $Iscc) { $cmd=Get-Command ISCC.exe -ErrorAction SilentlyContinue; if($cmd){$Iscc=$cmd.Source} }
if ($Iscc) { & $Iscc "/DMyAppVersion=$Version" "/DMyAppArch=$ArchLabel" .\windows_installer.iss; if($LASTEXITCODE -ne 0){throw "Inno Setup failed"} }
Write-Host "Windows portable ZIP: $Zip"
