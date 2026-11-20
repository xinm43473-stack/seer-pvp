# 构建 Windows 桌面版（onedir）：dist/desktop/SeerPeak.exe
# 用法: pwsh -File desktop/exe/build_exe.ps1
$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dist = Join-Path $proj 'dist\desktop'
$work = Join-Path $proj 'build\desktop'
$app  = Join-Path $work 'app'

Write-Output "[build] 清理旧产物"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $app 'references') | Out-Null

Write-Output "[build] 复制前端产物"
Copy-Item (Join-Path $proj 'references\spirit_synergy_view.html') (Join-Path $app 'references\spirit_synergy_view.html') -Force
Write-Output "[build] 镜像 assets（增量）"
robocopy (Join-Path $proj 'assets') (Join-Path $app 'assets') /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

$venv = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) '.buildtools\venv-exe'
if (-not (Test-Path $venv)) { $venv = 'E:\seerskill\.buildtools\venv-exe' }
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { throw "缺少 venv：$venv" }

Write-Output "[build] PyInstaller"
& $py -m PyInstaller --noconfirm --clean --windowed --onedir --name SeerPeak `
  --distpath $dist --workpath (Join-Path $work 'pyi') --specpath $work `
  --add-data "$app;app" `
  (Join-Path $PSScriptRoot 'launcher.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }

$exe = Join-Path $dist 'SeerPeak\SeerPeak.exe'
Write-Output ("[build] 完成: {0} ({1:N1} MB)" -f $exe, ((Get-ChildItem (Split-Path $exe) -Recurse -File | Measure-Object Length -Sum).Sum / 1MB))
