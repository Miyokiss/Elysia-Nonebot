@echo off
@REM ��ʾ
color 4
echo ������ǰ���3�������ļ�����
@REM ����yes
set /p input=������yes��
if "%input%"=="yes" (
    echo �����ļ��Ѽ�����
) else (
    echo �����ļ�δ�����ϣ��������������
    pause
    exit
)
set PATH=%PATH%;%cd%
@REM ���û��� �����ʹ���˼��ɻ������뽫python.exe��·����Ϊ���python.exe��·��
runtime\python.exe bot.py
pause
