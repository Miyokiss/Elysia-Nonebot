@echo off
@REM 提示
color 4
echo 你上线前检查3个配置文件了吗？
@REM 接收yes
set /p input=请输入yes：
if "%input%"=="yes" (
    echo 配置文件已检查完毕
) else (
    echo 配置文件未检查完毕，请检查后重新运行
    pause
    exit
)
set PATH=%PATH%;%cd%
@REM 配置环境 如果你使用了集成环境，请将python.exe的路径改为你的python.exe的路径
runtime\python.exe bot.py
pause
