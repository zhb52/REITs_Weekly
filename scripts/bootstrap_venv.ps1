# 在项目内建立虚拟环境并安装依赖，不污染系统 Python
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $root
try {
    if (-not (Test-Path '.venv')) {
        Write-Host '创建虚拟环境 .venv ...'
        python -m venv .venv
    }
    $py = Join-Path $root '.venv\Scripts\python.exe'
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.in
    & $py -m pip install -e .

    Write-Host ''
    Write-Host '自检：'
    & $py -c "import docx, matplotlib, pandas, numpy, yaml, openpyxl; print('  依赖 OK')"
    & $py -c "from matplotlib import font_manager as f; f.findfont('SimSun', fallback_to_default=False); print('  中文字体 SimSun OK')"
    & $py -m pytest -q
}
finally {
    Pop-Location
}
