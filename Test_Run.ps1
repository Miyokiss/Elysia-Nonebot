# ������������
$env:PYTHONUTF8 = "1"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"
[System.Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:Path += ";$pwd"
Write-Host "��������ģʽ - ��־�����ڷ�Ƭ���浽 logs\bot_YYYYMMDD.log" -ForegroundColor Cyan

# ������־Ŀ¼
New-Item -Path logs -ItemType Directory -Force > $null

# ִ�в�˫·�������ʱ�����
& {
    # ���û��� 
    .\runtime\python.exe .\bot.py 2>&1 | ForEach-Object {
        $currentDate = Get-Date -Format "yyyyMMdd"
        $logFile = "logs\bot_${currentDate}.log"
        $msg = "[$(Get-Date -Format 'HH:mm:ss')] $_"
        $msg | Tee-Object -FilePath $logFile -Append
    }
}

# ���ִ���
Read-Host "`n�� Enter �˳�..."