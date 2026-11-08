# dsh-pixelbar 卸载脚本
$ErrorActionPreference = 'Stop'

$prof = if ($env:DSH_PROFILE_DIR) { $env:DSH_PROFILE_DIR } else { Join-Path $env:USERPROFILE '.dsh\profiles\desktop' }

if (-not (Test-Path $prof)) {
  $base = Join-Path $env:USERPROFILE '.dsh\profiles'
  $cand = @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue)
  if ($cand.Count -eq 1) { $prof = $cand[0].FullName }
  else { throw "找不到 DSH profile 目录：$prof（可用环境变量 DSH_PROFILE_DIR 指定）" }
}

$dest    = Join-Path $prof 'node_modules\dsh-pixelbar'
$pkgPath = Join-Path $prof 'package.json'

if (Test-Path $dest) { Remove-Item $dest -Recurse -Force; "已删除 $dest" } else { '插件目录不存在，跳过' }

if (Test-Path $pkgPath) {
  $pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
  $pkg.dsh.profile.bundles = @(@($pkg.dsh.profile.bundles) | Where-Object { $_ -ne 'dsh-pixelbar' })
  $json = $pkg | ConvertTo-Json -Depth 40
  [System.IO.File]::WriteAllText($pkgPath, $json, (New-Object System.Text.UTF8Encoding($false)))
  '已从 dsh.profile.bundles 移除 dsh-pixelbar（备份见 package.json.pixelbar.bak）'
}
'完成：重启 DSH 后插件不再加载'
