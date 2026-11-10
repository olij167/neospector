$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Identity = Get-Content (Join-Path $Root 'app_source/release_identity.py') -Raw
$Match=[regex]::Match($Identity,'(?m)^VERSION\s*=\s*["''](?<v>[0-9]+\.[0-9]+\.[0-9]+(?:-ux[0-9]+)?)["'']')
if (-not $Match.Success) {throw 'A prepared release version is required'}
$Version=$Match.Groups['v'].Value
if ($Version -eq '0.7.25-ux41') {throw 'Prepare a new release version before building an installer'}
$Out=Join-Path $Root 'artifacts'
$Dist=Join-Path $Root 'native/dist'
$Build=Join-Path $Root 'native/pyinstaller-build'
New-Item -ItemType Directory -Force -Path $Out,$Dist,$Build | Out-Null
python -m pip install 'pyinstaller>=6.16,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3' 'tkinterdnd2>=0.4,<1' 'cryptography>=44,<48'
if ($LASTEXITCODE -ne 0) {throw 'Missing native build requirements'}
$Binaries=@()
foreach($Name in @('ffmpeg.exe','ffprobe.exe','ffplay.exe')) {
  $Command=Get-Command $Name -ErrorAction SilentlyContinue
  if ($Command) {$Binaries+=@('--add-binary',"$($Command.Source);tools")}
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) {throw 'FFmpeg missing'}
$Args=@('-m','PyInstaller','--noconfirm','--clean','--windowed','--name','Neospector',
  '--distpath',$Dist,'--workpath',$Build,'--specpath',(Join-Path $Root 'native'),
  '--paths',(Join-Path $Root 'app_source'),'--collect-all','tkinterdnd2',
  '--hidden-import','PIL._tkinter_finder','--add-data',"$(Join-Path $Root 'app_source/ui_profile.json');.") +
  $Binaries + @((Join-Path $Root 'app_source/neospector.py'))
python @Args
if ($LASTEXITCODE -ne 0) {throw 'Application freeze failed'}
$Exe=Join-Path $Dist 'Neospector/Neospector.exe'
if (-not (Test-Path $Exe)) {throw 'Missing application executable'}
python -m PyInstaller --noconfirm --clean --onefile --console --name NeospectorUpdater `
  --distpath $Dist --workpath $Build --specpath (Join-Path $Root 'native') `
  --paths (Join-Path $Root 'app_source') (Join-Path $Root 'app_source/native_installer_helper.py')
if ($LASTEXITCODE -ne 0) {throw 'Updater freeze failed'}
Move-Item -Force (Join-Path $Dist 'NeospectorUpdater.exe') (Join-Path $Dist 'Neospector/NeospectorUpdater.exe')
New-Item -ItemType Directory -Force -Path (Join-Path $Dist 'Neospector/updates') | Out-Null
Copy-Item -Force (Join-Path $Root 'updates/public.pem') (Join-Path $Dist 'Neospector/updates/public.pem')
$Thumb=(''+$env:NEOSPECTOR_WINDOWS_CERT_THUMBPRINT).Replace(' ','').ToUpperInvariant()
$Signed=$Thumb.Length -gt 0
if ($Signed) {
  if ($Thumb -notmatch '^[A-F0-9]{40}$') {throw 'Invalid Authenticode certificate thumbprint'}
  $SignTool=Get-Command signtool.exe -ErrorAction SilentlyContinue
  if (-not $SignTool) {throw 'signtool.exe required'}
  foreach($Target in @($Exe,(Join-Path $Dist 'Neospector/NeospectorUpdater.exe'))) {
    & $SignTool.Source sign /sha1 $Thumb /fd SHA256 /tr 'http://timestamp.digicert.com' /td SHA256 $Target
    if ($LASTEXITCODE -ne 0) {throw "Signing failed: $Target"}
    $Signature=Get-AuthenticodeSignature -LiteralPath $Target
    if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Thumbprint -ne $Thumb) {throw "Bad publisher identity: $Target"}
  }
}
$ISCC=Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $ISCC) {throw 'Inno Setup 6 is required for native installer'}
Push-Location (Join-Path $Root 'native')
try {
  if ($Signed) {
    $SignCommand='$q'+$SignTool.Source+'$q sign /sha1 '+$Thumb+' /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f'
    & $ISCC.Source ('/DNEOSPECTOR_VERSION='+$Version) '/DNEOSPECTOR_SIGNED' ('/Sneospector='+$SignCommand) windows_installer.iss
  } else {& $ISCC.Source ('/DNEOSPECTOR_VERSION='+$Version) windows_installer.iss}
  if ($LASTEXITCODE -ne 0) {throw 'Setup build failed'}
} finally {Pop-Location}
$Setup=Join-Path $Root ('native/dist-installer/Neospector_'+$Version+'_windows-x64_Setup.exe')
if (-not (Test-Path $Setup)) {throw 'Setup installer missing'}
if ($Signed) {
  $Signature=Get-AuthenticodeSignature -LiteralPath $Setup
  if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Thumbprint -ne $Thumb) {throw 'Setup publisher identity invalid'}
}
Copy-Item -Force $Setup $Out
$Destination=Join-Path $Out (Split-Path $Setup -Leaf)
(Get-FileHash -Algorithm SHA256 $Destination).Hash.ToLower()+'  '+(Split-Path $Destination -Leaf) | Out-File -Encoding ascii -FilePath ($Destination+'.sha256')
Write-Host ('Windows installer candidate: '+$Destination+'; '+$(if($Signed){'SIGNED'}else{'UNSIGNED PUBLIC TEST BUILD ONLY — not trusted for automatic updates'}))
