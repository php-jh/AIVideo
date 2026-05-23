@echo off
chcp 65001 >nul
title AI Short Drama Generator

echo 正在启动 AI Short Drama Generator...
echo.

:: 激活 video39 环境并运行
call F:\opt\conad\condabin\conda.bat activate video39
if errorlevel 1 (
    echo 激活环境失败，尝试直接运行...
)

:: 运行主程序
cd /d "%~dp0"
python main.py

:: 如果出错暂停
if errorlevel 1 (
    echo.
    echo 程序出错，请检查日志
    pause
)