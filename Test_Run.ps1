# ������������
$env:PYTHONUTF8 = "1"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"
[System.Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:Path += ";$pwd"
Write-Host "��������ģʽ - ��־ͬʱ��ʾ�����浽 logs\bot.log" -ForegroundColor Cyan

# ������־Ŀ¼
New-Item -Path logs -ItemType Directory -Force > $null

# ִ�в�˫·�������ʱ�����
& {
    # ���û��� �����ʹ���˼��ɻ������뽫python.exe��·����Ϊ���python.exe��·��
    .\runtime\python.exe .\bot.py 2>&1 | ForEach-Object {
        $msg = "[$(Get-Date -Format 'HH:mm:ss')] $_"
        $msg | Tee-Object -FilePath logs\bot.log -Append
    }
}

# ���ִ���
Read-Host "`n�� Enter �˳�..."