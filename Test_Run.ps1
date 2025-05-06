# 环境变量配置
$env:PYTHONUTF8 = "1"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"
[System.Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:Path += ";$pwd"
Write-Host "测试运行模式 - 日志按日期分片保存到 logs\bot_YYYYMMDD.log" -ForegroundColor Cyan

# 创建日志目录
New-Item -Path logs -ItemType Directory -Force > $null

# 执行并双路输出（带时间戳）
& {
    # 配置环境 
    .\runtime\python.exe .\bot.py 2>&1 | ForEach-Object {
        $currentDate = Get-Date -Format "yyyyMMdd"
        $logFile = "logs\bot_${currentDate}.log"
        $msg = "[$(Get-Date -Format 'HH:mm:ss')] $_"
        $msg | Tee-Object -FilePath $logFile -Append
    }
}

# 保持窗口
Read-Host "`n按 Enter 退出..."