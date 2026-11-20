# 安装打包工具链（JDK 17 + Android SDK + pywebview venv）到指定目录
# 用法: pwsh -NoProfile -File desktop/tools/install_toolchain.ps1 [-Root D:\ruanjianmen\dabao]
param([string]$Root = 'D:\ruanjianmen\dabao')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$JDK_URL = 'https://mirrors.huaweicloud.com/openjdk/17.0.2/openjdk-17.0.2_windows-x64_bin.zip'
$CMD_URL = 'https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-11076708_latest.zip'
$PIP_MIRROR = 'https://pypi.tuna.tsinghua.edu.cn/simple'

New-Item -ItemType Directory -Force -Path $Root | Out-Null
Write-Output "[tools] 目标目录 $Root"

function Get-File([string]$Url, [string]$Out) {
  if (Test-Path $Out) {
    Write-Output ("[tools] 已存在 {0}  {1:N1} MB" -f (Split-Path $Out -Leaf), ((Get-Item $Out).Length / 1MB))
    return
  }
  Write-Output "[tools] 下载 $Url"
  curl.exe -L --retry 3 --retry-delay 2 --progress-bar -o $Out $Url
  if ($LASTEXITCODE -ne 0) { throw "下载失败：$Url" }
  Write-Output ("[tools] 完成 {0:N1} MB" -f ((Get-Item $Out).Length / 1MB))
}

# 1) JDK
$jdkZip = Join-Path $Root 'jdk17.zip'
Get-File $JDK_URL $jdkZip
$jdkDir = Join-Path $Root 'jdk'
if (-not (Test-Path $jdkDir)) {
  Write-Output '[tools] 解压 JDK'
  Expand-Archive -Path $jdkZip -DestinationPath $jdkDir -Force
  Remove-Item $jdkZip -Force
}
$javaHome = Get-ChildItem $jdkDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'bin\javac.exe') } | Select-Object -First 1
if (-not $javaHome) { throw "JDK 解压后找不到 javac：$jdkDir" }
$env:JAVA_HOME = $javaHome.FullName
$env:PATH = (Join-Path $javaHome.FullName 'bin') + ';' + $env:PATH
Write-Output ("[tools] JDK {0}" -f ((& (Join-Path $javaHome.FullName 'bin\java.exe') -version 2>&1 | Select-Object -First 1)))

# 2) Android SDK cmdline-tools（必须位于 <sdk>\cmdline-tools\latest\）
$sdkRoot = Join-Path $Root 'sdk'
$ctZip = Join-Path $Root 'cmdline-tools.zip'
if (-not (Test-Path (Join-Path $sdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'))) {
  Get-File $CMD_URL $ctZip
  Write-Output '[tools] 解压 cmdline-tools'
  $tmp = Join-Path $Root 'ct_tmp'
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive -Path $ctZip -DestinationPath $tmp -Force
  New-Item -ItemType Directory -Force -Path (Join-Path $sdkRoot 'cmdline-tools') | Out-Null
  $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
  if ($inner) { Move-Item $inner.FullName (Join-Path $sdkRoot 'cmdline-tools\latest') }
  else { Move-Item $tmp (Join-Path $sdkRoot 'cmdline-tools\latest') }
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $ctZip -Force
}
$sdkm = Join-Path $sdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'
if (-not (Test-Path $sdkm)) { throw "缺少 sdkmanager：$sdkm" }

# 3) build-tools 与 platform
$need = @()
if (-not (Test-Path (Join-Path $sdkRoot 'build-tools\34.0.0\aapt2.exe'))) { $need += 'build-tools;34.0.0' }
if (-not (Test-Path (Join-Path $sdkRoot 'platforms\android-34\android.jar'))) { $need += 'platforms;android-34' }
if ($need.Count -gt 0) {
  $lic = Join-Path $Root 'licenses.txt'
  (1..300 | ForEach-Object { 'y' }) | Set-Content -Path $lic -Encoding ascii
  Write-Output ('[tools] 安装 ' + ($need -join ' '))
  cmd /c ('type "' + $lic + '" | "' + $sdkm + '" --sdk_root="' + $sdkRoot + '" ' + ($need -join ' '))
  if ($LASTEXITCODE -ne 0) { throw "sdkmanager 安装失败：$LASTEXITCODE" }
}

# 4) exe 用的 venv（pywebview + pyinstaller）
$venv = Join-Path $Root 'venv-exe'
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) {
  Write-Output '[tools] 创建 venv-exe'
  python -m venv $venv
}
Write-Output '[tools] 安装 pywebview + pyinstaller'
& $py -m pip install -q --upgrade pip --index-url $PIP_MIRROR
& $py -m pip install -q pywebview pyinstaller --index-url $PIP_MIRROR
if ($LASTEXITCODE -ne 0) { throw "pip 安装失败：$LASTEXITCODE" }

# 5) 自检
$okJdk = Test-Path (Join-Path $javaHome.FullName 'bin\javac.exe')
$okKey = Test-Path (Join-Path $javaHome.FullName 'bin\keytool.exe')
$okBt = Test-Path (Join-Path $sdkRoot 'build-tools\34.0.0\aapt2.exe')
$okPl = Test-Path (Join-Path $sdkRoot 'platforms\android-34\android.jar')
& $py -c "import webview, PyInstaller; print('pywebview+pyinstaller ok')"
$size = (Get-ChildItem $Root -Recurse -File -Force | Measure-Object Length -Sum).Sum
Write-Output ("[tools] 自检 javac={0} keytool={1} build-tools={2} platform={3}" -f $okJdk, $okKey, $okBt, $okPl)
Write-Output ("[tools] 完成，占用 {0:N1} MB" -f ($size / 1MB))
if (-not ($okJdk -and $okKey -and $okBt -and $okPl)) { throw '工具链自检未通过' }
