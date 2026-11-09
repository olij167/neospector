$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
python scripts/prepare_source.py --verify-only
if ($LASTEXITCODE -ne 0) { throw 'Source verification failed' }
$Extract = Join-Path $Root 'build-work/source'
if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
python scripts/prepare_source.py --output $Extract
if ($LASTEXITCODE -ne 0) { throw 'Source extraction failed' }
$Src = Join-Path $Extract 'Neospector_UX41_Final_Reactions_PingPong_20261109'
python -m pip install 'pyinstaller>=6.16,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3' 'tkinterdnd2>=0.4,<1'
if ($LASTEXITCODE -ne 0) { throw 'Native build dependencies failed' }
$Commands = @('ffmpeg.exe','ffprobe.exe','ffplay.exe')
$BinArgs = @()
foreach ($name in $Commands) {
  $Cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($Cmd) { $BinArgs += @('--add-binary', "$($Cmd.Source);tools") }
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) { throw 'FFmpeg is required to package media playback' }
$dist = Join-Path $Root 'native\dist'
$build = Join-Path $Root 'native\pyinstaller-build'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$PyArgs = @('-m','PyInstaller','--noconfirm','--clean','--windowed','--name','Neospector',
  '--distpath',$dist,'--workpath',$build,'--specpath',(Join-Path $Root 'native'),
  '--paths',(Join-Path $Src 'app_source'),
  '--hidden-import','PIL._tkinter_finder','--collect-all','tkinterdnd2',
  '--add-data',"$(Join-Path $Src 'examples');examples",
  '--add-data',"$(Join-Path $Src 'app_source\ui_profile.json');.",
  '--add-data',"$(Join-Path $Src 'updates\public.pem');updates") + $BinArgs + @((Join-Path $Src 'app_source\neospector.py'))
python @PyArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$Exe=Join-Path $dist 'Neospector\Neospector.exe'
if (-not (Test-Path $Exe)) { throw 'Missing Neospector.exe' }
$Portable=Join-Path $Root 'artifacts\Neospector_0.7.25-ux41_windows-x64_Portable.zip'
New-Item -ItemType Directory -Force -Path (Split-Path $Portable) | Out-Null
Compress-Archive -Path "$dist\Neospector\*" -DestinationPath $Portable -CompressionLevel Optimal -Force
$Iscc=(Get-Command ISCC.exe -ErrorAction SilentlyContinue)
if (-not $Iscc) {
  $Candidates=@("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe","$env:ProgramFiles\Inno Setup 6\ISCC.exe")
  $Location=$Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
} else { $Location=$Iscc.Source }
if (-not $Location) { throw 'Inno Setup 6 is REQUIRED; refusing to call portable ZIP a wizard installer' }
$Native=Join-Path $Root 'native'
Push-Location $Native
try { & $Location 'windows_installer.iss' } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
$Setup=Join-Path $Native 'dist-installer\Neospector_0.7.25-ux41_windows-x64_Setup.exe'
if (-not (Test-Path $Setup)) { throw 'Missing Setup.exe' }
Copy-Item -Force $Setup (Join-Path $Root 'artifacts')
foreach ($p in @($Portable,(Join-Path $Root 'artifacts\Neospector_0.7.25-ux41_windows-x64_Setup.exe'))) {
  $h=(Get-FileHash -Algorithm SHA256 $p).Hash.ToLower()
  "$h  $(Split-Path $p -Leaf)" | Set-Content -Encoding ascii "$p.sha256"
}
Write-Host 'NATIVE WINDOWS BUILD CANDIDATE: hardware acceptance and code signing still required.'
