# 提交打包：生成 studentID-final-project.zip，包含完整 .git 历史
#
# 为什么不用 Compress-Archive：它在部分 PowerShell 版本下会跳过以点开头的
# 隐藏目录（.git、.github），导致提交包里没有历史，而作业明确要求必须包含。
# 这里用 .NET 的 ZipFile::CreateFromDirectory，它对隐藏文件一视同仁。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\package_submission.ps1 -StudentId 25210660117

param(
    [Parameter(Mandatory = $true)]
    [string]$StudentId,

    [string]$SourceDir = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$OutDir    = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zipPath = Join-Path $OutDir "$StudentId-final-project.zip"

# ---- 前置检查 ----------------------------------------------------------
if (-not (Test-Path (Join-Path $SourceDir '.git'))) {
    throw "源目录下没有 .git，无法提交完整历史：$SourceDir"
}

Push-Location $SourceDir
try {
    $dirty = git status --porcelain
    if ($dirty) {
        Write-Warning "工作区有未提交的改动，先提交再打包："
        $dirty | ForEach-Object { Write-Host "  $_" }
        throw "请先 git add -A; git commit 后再运行本脚本"
    }

    $head = git rev-parse --short HEAD
    $count = git rev-list --count HEAD
    $shallow = git rev-parse --is-shallow-repository
    Write-Host "提交 $count 条，HEAD=$head，浅克隆=$shallow"
    if ($shallow -eq 'true') {
        throw "当前是浅克隆，作业不接受。请先 git fetch --unshallow"
    }

    # 凭证检查：.git/config 里不得出现 token 或带密码的 URL
    $cfg = Get-Content (Join-Path $SourceDir '.git\config') -Raw
    if ($cfg -match '(?i)token|password|https://[^/\s]+:[^@\s]+@') {
        throw "检测到 .git/config 中含凭证，先清理再打包"
    }
}
finally {
    Pop-Location
}

# ---- 打包 --------------------------------------------------------------
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# 在源目录的父目录下暂存一份干净副本，避免把 .venv 等大目录打进去
$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("reits-pack-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null

$excludeDirs = @('.venv', '__pycache__', '.pytest_cache', 'node_modules')
try {
    Get-ChildItem -Path $SourceDir -Force | Where-Object {
        $_.Name -ne '.venv' -and $_.Name -ne '__pycache__' -and $_.Name -ne '.pytest_cache'
    } | ForEach-Object {
        Copy-Item $_.FullName -Destination $staging -Recurse -Force
    }

    # 清掉副本里的缓存目录（.git 必须保留）
    Get-ChildItem -Path $staging -Recurse -Directory -Force |
        Where-Object { $excludeDirs -contains $_.Name } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $staging, $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false   # 不包含顶层目录，解压后直接是项目文件
    )
}
finally {
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- 验证 --------------------------------------------------------------
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $names = $zip.Entries | ForEach-Object { $_.FullName }
    $hasGitHead  = $names -contains '.git/HEAD'
    $hasGitObjs  = ($names | Where-Object { $_ -like '.git/objects/*' }).Count -gt 0
    $hasGit      = $hasGitHead -and $hasGitObjs
    $fileCount   = $names.Count
}
finally {
    $zip.Dispose()
}

$sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)

Write-Host ""
Write-Host "已生成：$zipPath"
Write-Host "  文件数   $fileCount"
Write-Host "  大小     $sizeMb MB"
Write-Host "  .git/    $(if ($hasGit) { '完整（含 HEAD 与 objects）' } else { '缺失或损坏' })"

if (-not $hasGit) {
    throw "压缩包里没有完整的 .git，不满足提交要求"
}

Write-Host ""
Write-Host "自检通过：完整历史已包含，可在不访问远程仓库的情况下审阅。"
