# dsh-pixelbar 安装脚本（在 DSH 之外运行）
# 作用：把插件复制进 DSH profile 的 node_modules，并把 dsh-pixelbar 登记为 bundle。
$ErrorActionPreference = 'Stop'

$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$prof = if ($env:DSH_PROFILE_DIR) { $env:DSH_PROFILE_DIR } else { Join-Path $env:USERPROFILE '.dsh\profiles\desktop' }

# profile 目录不存在时：唯一候选就自动选，多个就报错让人指定
if (-not (Test-Path $prof)) {
  $base = Join-Path $env:USERPROFILE '.dsh\profiles'
  $cand = @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue)
  if ($cand.Count -eq 1) {
    $prof = $cand[0].FullName
  } else {
    throw "找不到 DSH profile 目录：$prof`n可用环境变量 DSH_PROFILE_DIR 指定，例如：`n  `$env:DSH_PROFILE_DIR='$base\<profile>'; .\apply.ps1"
  }
}

$dest    = Join-Path $prof 'node_modules\dsh-pixelbar'
$pkgPath = Join-Path $prof 'package.json'

if (-not (Test-Path $pkgPath)) { throw "找不到 profile 的 package.json：$pkgPath" }

# python：PATH 上找，找不到就明确报错
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { throw 'PATH 上找不到 python，请先安装 Python 3（安装时勾选 Add python.exe to PATH）' }

# hid 依赖检查（只警告，不阻断）
& $pyCmd.Source -c 'import hid' 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Warning "python 缺少 hid 库，运行前请执行：`"$($pyCmd.Source)`" -m pip install hidapi"
}

$script = Join-Path $src 'scripts\halo_pixelbar.py'
if (-not (Test-Path $script)) { throw "插件不完整，找不到 scripts\halo_pixelbar.py" }

# 1) 复制插件文件
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($f in @('index.js', 'package.json', 'cordis.patch.yml', 'README.md', 'LICENSE')) {
  if (Test-Path (Join-Path $src $f)) { Copy-Item (Join-Path $src $f) $dest -Force }
}
# 只复制 .py，跳过 __pycache__ 等中间产物
$destScripts = Join-Path $dest 'scripts'
New-Item -ItemType Directory -Force $destScripts | Out-Null
Copy-Item (Join-Path $src 'scripts\*.py') $destScripts -Force
"[1/2] 已复制插件到 $dest"
"[i] python = $($pyCmd.Source)"

# 2) 登记 bundle（先备份 package.json）
Copy-Item $pkgPath "$pkgPath.pixelbar.bak" -Force
$pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
if ($null -eq $pkg.dsh -or $null -eq $pkg.dsh.profile) { throw 'profile package.json 缺少 dsh.profile 字段，未做改动' }
$bundles = @($pkg.dsh.profile.bundles)
if ($bundles -notcontains 'dsh-pixelbar') {
  $pkg.dsh.profile.bundles = @($bundles + 'dsh-pixelbar')
  $json = $pkg | ConvertTo-Json -Depth 40
  [System.IO.File]::WriteAllText($pkgPath, $json, (New-Object System.Text.UTF8Encoding($false)))
  '[2/2] 已把 dsh-pixelbar 加入 dsh.profile.bundles'
} else {
  '[2/2] bundle 已登记，跳过'
}

'完成：重启 DSH 后 pixelbar 工具生效。撤销请运行 rollback.ps1'
