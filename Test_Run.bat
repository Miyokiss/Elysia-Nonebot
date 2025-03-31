@echo off
@REM 提示
set PATH=%PATH%;%cd%
@REM 配置环境 如果你使用了集成环境，请将python.exe的路径改为你的python.exe的路径
runtime\python.exe bot.py
pause
