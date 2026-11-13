@echo off
chcp 65001 >nul
title 《暗黑破坏神2：重制版》DD373 智能比价与上架系统 - 环境一键部署工具

echo ============================================================================
echo   正在检查 Windows 10 运行环境并初始化项目...
echo ============================================================================

:: 1. 检查 Python 是否已安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.11 (64位) 并勾选 Add to PATH。
    pause
    exit /b 1
)

:: 2. 设置 HuggingFace 国内镜像环境变量（加速本地 bge-m3 向量模型下载）
set HF_ENDPOINT=https://hf-mirror.com

:: 3. 创建独立虚拟环境 (.venv)
if not exist ".venv" (
    echo [1/4] 正在创建独立 Python 虚拟环境 (.venv)...
    python -m venv .venv
) else (
    echo [1/4] 检测到虚拟环境已存在，跳过创建。
)

:: 4. 激活虚拟环境并安装依赖
echo [2/4] 正在使用国内镜像源安装核心依赖包 (PySide6, AI, 爬虫组件)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -i https://tsinghua.edu.cn
pip install -r requirements.txt -i https://tsinghua.edu.cn

:: 5. 安装 Playwright 备用无头浏览器内核
echo [3/4] 正在检查并安装 Chromium 无头浏览器内核...
playwright install chromium

:: 6. 执行 Python 项目目录与 SQLite 数据库初始化脚本
echo [4/4] 正在初始化本地工作目录树与 SQLite 核心数据库...
python init_project.py

echo.
echo ============================================================================
echo   🎉 全部环境与数据库初始化完成！
echo   提示：请确保已在 Windows 中安装 Ollama 并执行过: ollama pull qwen3-vl:8b
echo ============================================================================
pause
