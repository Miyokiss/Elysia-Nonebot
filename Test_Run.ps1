# 环境变量配置
$env:PYTHONUTF8 = "1"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"
[System.Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:Path += ";$pwd"
Write-Host "测试运行模式 - 日志同时显示并保存到 logs\bot.log" -ForegroundColor Cyan

# 创建日志目录
New-Item -Path logs -ItemType Directory -Force > $null

# 执行并双路输出（带时间戳）
& {
    # 配置环境 如果你使用了集成环境，请将python.exe的路径改为你的python.exe的路径
    .\runtime\python.exe .\bot.py 2>&1 | ForEach-Object {
        $msg = "[$(Get-Date -Format 'HH:mm:ss')] $_"
        $msg | Tee-Object -FilePath logs\bot.log -Append
    }
}

# 保持窗口
Read-Host "`n按 Enter 退出..."