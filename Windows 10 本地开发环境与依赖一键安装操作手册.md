# 《暗黑破坏神2：重制版》DD373 智能比价与上架系统 — Windows 10 本地环境安装手册

> **适用环境**：Windows 10 专业版（64位） + NVIDIA RTX 4060 Ti 显卡  
> **目标目录**：`D:\D2R_AutoTrade`

---

## 第一阶段：安装两大底层基础软件（仅需执行一次）

### 1. 安装 Python 3.11（64位）
1. 前往 Python 官网下载 **Python 3.11.x (Windows installer 64-bit)** 安装包。
2. 双击运行安装程序，**【极其重要】**在安装界面最底部必须勾选 **`Add python.exe to PATH`**（将 Python 加入系统环境变量），然后点击 `Install Now` 完成安装。
3. **验证安装**：按键盘 `Win + R`，输入 `cmd` 回车，输入以下命令并回车：
   ```cmd
   python --version
   ```
   若屏幕输出 `Python 3.11.x`，说明安装成功。

### 2. 安装本地大模型引擎 Ollama 并拉取视觉模型
1. 前往 Ollama 官网（`ollama.com`）下载 **Ollama for Windows** 安装包并完成安装（安装后 Windows 右下角托盘会出现小羊驼图标，它会自动识别你的 RTX 4060 Ti 显卡）。
2. 打开命令提示符（CMD）或 PowerShell，执行以下命令下载《暗黑2》截图识别主力模型（约 5.2GB，支持断点续传）：
   ```cmd
   ollama pull qwen3-vl:8b
   ```
3. **验证模型**：下载完成后，执行以下命令确认模型在列表中即可（平时不运行不占显存）：
   ```cmd
   ollama list
   ```

---

## 第二阶段：创建项目根目录与独立 Python 虚拟环境

为防止依赖包与电脑里其他软件冲突，我们在 `D:\D2R_AutoTrade` 下创建完全独立的隔离环境：

1. 在电脑 D 盘根目录下新建文件夹：**`D:\D2R_AutoTrade`**。
2. 打开该文件夹，在文件夹顶部的地址栏中直接输入 **`powershell`** 并按回车，即可直接在当前目录下打开蓝色 PowerShell 终端窗口。
3. 在 PowerShell 中依次复制粘贴并回车执行以下两条命令：

```powershell
# 1. 创建名为 .venv 的独立虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
.\.venv\Scripts\activate
```

> **常见报错提示**：如果激活时提示“在此系统上禁止运行脚本（ExecutionPolicy 报错）”，请执行下面这行解除限制命令（输入 `Y` 确认），然后再重新运行上面的第 2 条激活命令即可：
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> 当你看到命令行最前面出现绿色的 **`(.venv)`** 字样时，说明虚拟环境已成功激活！

---

## 第三阶段：配置并批量安装 Python 核心依赖

### 1. 创建依赖清单文件 (`requirements.txt`)
在 `D:\D2R_AutoTrade\` 目录下新建一个文本文档，将其重命名为 **`requirements.txt`**（注意确认文件后缀是 `.txt`，不是 `.txt.txt`），将以下完整依赖内容复制粘贴进去并保存：

```text
# 1. Windows 10 桌面 UI、现代组件与内嵌谷歌浏览器
PySide6>=6.7.0
PySide6-Fluent-Widgets>=1.6.0
PyQtGraph>=0.13.7

# 2. 爬虫采集与反爬指纹模拟
curl_cffi>=0.7.0
playwright>=1.45.0
playwright-stealth>=1.0.6
tenacity>=8.5.0

# 3. AI 交互、本地内存向量模型与结构化校验
openai>=1.40.0
instructor>=1.4.0
pydantic>=2.8.0
sentence-transformers>=3.0.0
chromadb>=0.5.5
Pillow>=10.4.0

# 4. 定时任务调度与基础工具
APScheduler>=3.10.4
python-dotenv>=1.0.1
```

### 2. 使用国内清华镜像源高速安装所有依赖
保持 PowerShell 处于 **`(.venv)`** 激活状态，执行以下升级与批量安装命令（使用国内镜像源，下载速度极快）：

```powershell
# 1. 升级 pip 包管理器到最新版
python -m pip install --upgrade pip -i https://tsinghua.edu.cn

# 2. 一键安装 requirements.txt 中的全部依赖库
pip install -r requirements.txt -i https://tsinghua.edu.cn
```

### 3. 安装 Playwright 备用无头浏览器内核
等上一步所有库安装完毕后，继续在当前窗口执行以下命令，下载用于极端反爬兜底的 Chromium 浏览器内核：

```powershell
playwright install chromium
```

---

## 第四阶段：环境安装总验收自检

全部执行完毕后，在 PowerShell 中运行以下一键自检命令，验证核心组件是否均能正常导入：

```powershell
python -c "import PySide6, qfluentwidgets, pyqtgraph, curl_cffi, playwright, openai, instructor, sentence_transformers, chromadb; print('🎉 所有核心依赖安装成功，Windows 10 开发环境已就绪！')"
```

如果终端顺利打印出 **`🎉 所有核心依赖安装成功，Windows 10 开发环境已就绪！`**，说明你的本地全栈 AI 开发环境已经 100% 搭建完成！

---

## 补充提示：本地嵌入模型 (`BAAI/bge-m3`) 首次下载加速
由于 `BAAI/bge-m3` 向量模型存储在 HuggingFace 上，国内直连下载可能较慢。建议在 Windows 系统环境变量中添加一条国内镜像加速变量（仅需配置一次）：
* **变量名**：`HF_ENDPOINT`
* **变量值**：`https://hf-mirror.com`

配置后，首次运行程序时系统会自动从国内镜像秒速下载 `BAAI/bge-m3` 到本地缓存，后续永久离线运行在系统内存中（0 显存占用）。
