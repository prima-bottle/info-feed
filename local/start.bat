@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title 信息台本地助手
python local\worker.py
pause
