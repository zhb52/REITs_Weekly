# 在项目内建立虚拟环境并安装依赖，不污染系统 Python
#
# 关于输出语言：pip 的输出不换行，且会改变控制台输出编码而不还原，
# 导致紧随其后的中文在部分终端里显示为乱码。因此本脚本的中文提示只出现在
# pip 运行之前，pip 之后的提示一律用 ASCII —— 这样任何代码页下都能读。
$ErrorActionPreference = 'Stop'

# $PSScriptRoot 在 -File 方式下始终可用；$MyInvocation.MyCommand.Path 在
# 参数默认值或某些调用方式下可能为空。
$root = Split-Path -Parent $PSScriptRoot

Write-Host '开始准备环境：依赖装在项目内的 .venv，不影响系统 Python'
Write-Host 'Installing into the project-local .venv (system Python untouched)'

Push-Location $root
try {
    if (-not (Test-Path '.venv')) {
        python -m venv .venv
    }
    $py = Join-Path $root '.venv\Scripts\python.exe'
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.in
    & $py -m pip install -e .

    $env:PYTHONIOENCODING = 'utf-8'
    Write-Host ''
    Write-Host '--- self check ---'

    & $py -c "import docx, matplotlib, pandas, numpy, yaml, openpyxl"
    if ($LASTEXITCODE -eq 0) { Write-Host '[ok] dependencies' }
    else { throw 'dependency install failed, see pip output above' }

    & $py -c "from matplotlib import font_manager as f; f.findfont('SimSun', fallback_to_default=False)"
    if ($LASTEXITCODE -eq 0) { Write-Host '[ok] CJK font SimSun' }
    else { Write-Host '[warn] SimSun not found; charts fall back to Microsoft YaHei' }

    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'tests failed; fix before running the pipeline' }
    Write-Host '[ok] tests'
    Write-Host ''
    Write-Host '--- next ---'
    Write-Host '  .\.venv\Scripts\python.exe -m reits_weekly.cli run'
}
finally {
    Pop-Location
}
