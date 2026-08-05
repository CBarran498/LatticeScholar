# LatticeScholar 本地安装与使用完整指南

> 本文档面向下载了 [LatticeScholar](https://github.com/CBarran498/LatticeScholar) 后不知道如何在本地电脑上运行的用户。覆盖 macOS、Windows、Linux 三个平台，从零开始，逐步引导到安装、启动和日常使用。

---

## 最快上手：免安装桌面版（不需要 Python）

如果你不想安装 Python 和任何开发工具，可以直接下载打包好的桌面版：

1. 打开 [GitHub Releases](https://github.com/CBarran498/LatticeScholar/releases) 页面
2. 下载对应你电脑平台的压缩包：
   - **macOS** (M1/M2/M3/M4 及 Intel)：`LatticeScholar-macos-arm64.tar.gz`
   - **Windows 10/11** (64 位)：`LatticeScholar-windows-x64.zip`
   - **Linux x64** (Ubuntu 22.04+/Debian 12+/Fedora 38+)：`LatticeScholar-linux-x64.tar.gz`
3. 解压后双击 `LatticeScholar`（Windows 上是 `LatticeScholar.exe`）
4. 浏览器自动打开，即可使用

> **macOS Intel 用户**：下载 ARM64 版本即可，macOS 通过 Rosetta 2 自动翻译运行，无需额外操作。
>
> **macOS 首次打开**如果提示"无法验证开发者"：右键点击 → 打开 → 确认；或在终端执行 `xattr -cr LatticeScholar/`。
>
> **Windows 首次打开**如果提示"Windows 已保护你的电脑"（SmartScreen）：点击"更多信息" → "仍要运行"。建议将文件解压到不含中文和空格的路径（如 `D:\LatticeScholar\`）。

数据保存在用户主目录的 `.latticescholar` 文件夹中（macOS/Linux 为 `~/.latticescholar/`，Windows 为 `C:\Users\你的用户名\.latticescholar\`）。

**桌面版系统要求**：macOS 12+、Windows 10+ (64 位)、Linux x64 (glibc 2.35+)。不满足要求的系统（Windows 7/8、32 位、Linux ARM64 等）请使用下方的"从源码运行"方式，只需 Python 3.9+。

如果桌面版满足你的需求，下面的 Python 安装步骤可以跳过。如果你需要从源码运行、参与开发或使用高级 PDF 引擎，请继续阅读。

---

## 目录

- [一、前提条件：安装 Python](#一前提条件安装-python)
- [二、下载项目代码](#二下载项目代码)
- [三、安装与启动](#三安装与启动)
  - [macOS / Linux](#macos--linux)
  - [macOS 双击启动](#macos-双击启动更简单的方式)
  - [Windows PowerShell](#windows-powershell)
  - [Windows CMD 命令提示符](#windows-cmd-命令提示符)
  - [Docker 启动](#docker-启动替代方式)
- [四、启动成功后你会看到什么](#四启动成功后你会看到什么)
- [五、基本使用流程](#五基本使用流程)
- [六、连接 AI 模型（可选增强）](#六连接-ai-模型可选增强)
  - [通过网页模型控制台连接](#方式-a通过网页模型控制台连接推荐)
  - [通过环境变量配置](#方式-b通过环境变量配置)
- [七、配置学术数据源（可选）](#七配置学术数据源可选提高检索质量)
- [八、使用 .env 文件管理配置](#八使用-env-文件管理配置推荐)
- [九、高级 PDF 解析（可选）](#九高级-pdf-解析可选)
- [十、日常使用：停止与再次启动](#十日常使用停止与再次启动)
- [十一、更新到最新版本](#十一更新到最新版本)
- [十二、常见问题](#十二常见问题)
- [十三、命令速查表](#十三命令速查表)

---

## 一、前提条件：安装 Python

LatticeScholar 需要 **Python 3.9 或更高版本**。

### 检查是否已安装

打开终端（macOS/Linux）或 PowerShell/命令提示符（Windows），输入：

```bash
python3 --version
```

Windows 上也可以用：

```powershell
python --version
```

如果显示 `Python 3.9.x` 或更高版本号，说明已经安装好了，可以跳到下一步。

### 未安装 Python 的解决方法

| 平台 | 安装方式 |
|---|---|
| **macOS** | 前往 https://www.python.org/downloads/ 下载安装包；或使用 Homebrew：`brew install python` |
| **Windows** | 前往 https://www.python.org/downloads/ 下载安装包。**安装时务必勾选 "Add Python to PATH"** |
| **Ubuntu / Debian** | `sudo apt update && sudo apt install python3 python3-venv python3-pip` |
| **CentOS / Fedora** | `sudo dnf install python3` |

---

## 二、下载项目代码

### 方式 A：使用 Git 克隆（推荐）

```bash
git clone https://github.com/CBarran498/LatticeScholar.git
```

克隆完成后会在当前目录下创建 `LatticeScholar` 文件夹。

### 方式 B：下载 ZIP 压缩包

1. 在浏览器中打开 https://github.com/CBarran498/LatticeScholar
2. 点击绿色的 **"Code"** 按钮
3. 选择 **"Download ZIP"**
4. 下载完成后，解压到你想存放的位置

> **建议**：优先使用 Git 克隆，后续更新代码只需一条命令。ZIP 下载的方式每次更新都需要重新下载。

---

## 三、安装与启动

### macOS / Linux

打开终端（macOS 中按 `Command + 空格` 搜索"终端"），依次输入以下命令：

```bash
# 第 1 步：进入项目目录（根据实际路径调整）
cd LatticeScholar

# 第 2 步：创建 Python 虚拟环境（只需执行一次）
python3 -m venv .venv

# 第 3 步：激活虚拟环境
source .venv/bin/activate

# 第 4 步：安装项目及其所有依赖（只需执行一次）
pip install -e .

# 第 5 步：启动服务
latticescholar
```

启动后终端会显示类似以下信息：

```
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

浏览器会自动打开。如果没有自动打开，手动在浏览器地址栏输入：

> **http://127.0.0.1:8765**

### macOS 双击启动（更简单的方式）

项目根目录有一个 `启动 LatticeScholar.command` 文件，它会自动完成创建虚拟环境、安装依赖、启动服务的全部步骤。

1. 在访达（Finder）中找到项目文件夹
2. 双击 `启动 LatticeScholar.command`
3. 如果系统提示"无法打开"或"来自身份不明的开发者"，右键点击该文件 → 选择"打开" → 点击"打开"确认
4. 等待终端窗口出现，安装完成后浏览器会自动打开

### Windows PowerShell

按 `Win + X` 选择"Windows PowerShell"或"终端"，依次输入：

```powershell
# 第 1 步：进入项目目录
cd LatticeScholar

# 第 2 步：创建虚拟环境（只需执行一次）
py -m venv .venv

# 第 3 步：激活虚拟环境
.venv\Scripts\Activate.ps1

# 第 4 步：安装项目（只需执行一次）
pip install -e .

# 第 5 步：启动
latticescholar
```

> **如果 PowerShell 提示"无法运行脚本"**，先执行以下命令，然后重新执行第 3 步：
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### Windows CMD 命令提示符

按 `Win + R`，输入 `cmd` 回车，依次输入：

```cmd
cd LatticeScholar
py -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
latticescholar
```

### Docker 启动（替代方式）

如果你已经安装了 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，可以跳过 Python 环境配置，用 Docker 一键启动：

```bash
cd LatticeScholar
docker compose up -d --build
```

启动后访问 http://127.0.0.1:8765 即可。数据保存在 Docker 卷 `latticescholar-data` 中，删除容器不会丢失数据。

如需停止：

```bash
docker compose down
```

---

## 四、启动成功后你会看到什么

打开 http://127.0.0.1:8765 后，界面左侧导航栏包含以下功能模块：

| 模块 | 功能说明 |
|---|---|
| **总览** | 首页，显示项目概况 |
| **科研项目** | 以研究课题为核心，管理检索轨迹、证据数量和项目状态 |
| **文献雷达** | 多数据源文献检索（Crossref、Semantic Scholar、arXiv、OpenAlex、PubMed） |
| **论文深度解剖** | 上传论文 PDF，用四个核心问题深度解析论文 |
| **期刊匹配** | 根据相关论文样本聚合候选期刊与 DOI 证据 |
| **政策雷达** | 查看 32 个跨行业官方政策源的科研政策信号 |
| **Idea Lab** | 结合文献边界与政策信号，生成可证伪的研究假设 |
| **科研研讨室** | 围绕当前课题、证据库和已选政策讨论研究问题 |
| **我的证据库** | 收藏论文、管理证据，支持 Markdown/BibTeX/RIS 导出 |
| **科研任务台** | 将下一步变成可交付、可检查的科研任务 |
| **模型控制台** | 连接和管理 AI 模型服务 |
| **使用指南** | 内置使用帮助 |

**默认模式为 `accounts`（邮箱登录）**——首次打开会看到邮箱登录页。输入任意邮箱后，验证码会直接显示在页面上（本地未配置 SMTP 时自动启用开发模式），输入验证码即可进入工作台。建议在 `.env` 中设置 `LATTICE_ADMIN_EMAILS=your@email.edu` 以获得管理员（Pro）权益。不需要配置任何模型，所有本地能力开箱即用。

---

## 五、基本使用流程

### 第 1 步：创建科研项目

1. 点击左侧 **"科研项目"**
2. 创建一个新课题
3. 填写研究对象、场景、约束和希望验证的关系
4. 这个项目将成为后续所有检索、分析、Idea 的容器

### 第 2 步：文献检索

1. 点击 **"文献雷达"**
2. 分别填写：
   - **中文研究主题**：用完整的句子描述你的研究问题
   - **英文检索式**：核心概念、同义词、缩写和技术名词
3. 点击搜索，系统会同时查询多个开放学术数据源
4. 有摘要的结果可直接阅读和收藏；仅题录的结果需通过 DOI 或合法渠道获取原文
5. 也可以从知网、Google Scholar 或 Web of Science 导出 BibTeX/RIS 文件后导入

### 第 3 步：论文深度解剖

1. 点击 **"论文深度解剖"**
2. 上传合法获取的论文 PDF 文件
3. 系统会从四个核心维度解析论文：
   - 这个领域的痛点是什么？
   - 相对经典工作做了什么改动？
   - 实验是否充分？
   - 必须回原文深挖之处
4. 每个问题以"一句结论 + 分条详答 + 页码位置"呈现
5. 所有解释使用简体中文，引文保留原文语言

### 第 4 步：收藏到证据库

- 在搜索结果或分析中，将有价值的论文和证据保存到 **"我的证据库"**
- 支持导出为 Markdown、BibTeX、RIS 格式，方便引用管理

### 第 5 步：生成研究 Idea

1. 点击 **"Idea Lab"**
2. 可以手动描述前期工作，也可以上传已有文件（支持 PDF、Word、PPT、Excel、Markdown、LaTeX、Jupyter Notebook、BibTeX、RIS 等）
3. 结合已有文献证据和政策信号，系统会生成包含假设、风险和首轮验证方案的研究方向

### 第 6 步：科研研讨

1. 点击 **"科研研讨室"**
2. 围绕当前课题和收集的证据进行研究讨论
3. 系统只引用你的真实证据库中的证据，不会凭空杜撰

---

## 六、连接 AI 模型（可选增强）

> **重要提示**：不配置任何 AI 模型，文献检索、去重、缓存、规则分析和结构化 Idea 等核心功能**完全正常可用**，云 Token 消耗为 0。配置模型是可选的增强，可以提升论文解剖、Idea 生成和科研研讨的深度。

### 方式 A：通过网页"模型控制台"连接（推荐）

这是最简单的方式，不需要编辑任何配置文件：

1. 点击左侧 **"模型控制台"**
2. 选择你想连接的服务商
3. 点击"连接服务"
4. 输入你从服务商**官方控制台**获取的 API Key
5. 核对 Base URL 和模型名称
6. 点击"加密保存"
7. 点击该服务商卡片上的"测试"按钮验证连接

支持的 16 类模型服务：

| 分类 | 服务商 |
|---|---|
| 国内 | DeepSeek、通义千问、智谱 GLM、Kimi、MiniMax、腾讯混元、豆包/火山方舟、百度千帆 |
| 国际 | OpenAI、Anthropic Claude、Google Gemini、Mistral、Cohere、xAI Grok |
| 聚合与本地 | OpenRouter、Ollama / 校内 OpenAI-compatible 网关 |

### 方式 B：通过环境变量配置

在终端中启动服务**之前**设置环境变量。以下是几个典型场景：

#### 场景 1：使用 DeepSeek（推荐国内用户）

```bash
export LATTICE_LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-你的密钥
export LATTICE_ALLOW_REMOTE_LLM=true
export LATTICE_DEEPSEEK_ROUTING=balanced
latticescholar
```

路由策略说明：
- `economy`：全部任务使用快速模型（最省钱）
- `balanced`：检索用快速模型，论文解剖/Idea/研讨用深度模型（推荐）
- `quality`：全部任务使用深度模型

#### 场景 2：使用本地 Ollama（完全离线，隐私最强）

1. 先安装 [Ollama](https://ollama.com/) 并启动
2. 下载一个模型：`ollama pull qwen2.5:7b`
3. 然后启动 LatticeScholar：

```bash
export LATTICE_LLM_PROVIDER=ollama
export LATTICE_LLM_BASE_URL=http://127.0.0.1:11434
export LATTICE_LLM_MODEL=qwen2.5:7b
latticescholar
```

#### 场景 3：使用 OpenAI 兼容接口

```bash
export LATTICE_LLM_PROVIDER=openai_compatible
export LATTICE_LLM_BASE_URL=https://api.openai.com/v1
export LATTICE_LLM_API_KEY=sk-你的密钥
export LATTICE_LLM_MODEL=gpt-4o
export LATTICE_ALLOW_REMOTE_LLM=true
latticescholar
```

> **安全提醒**：不要提交密钥到 Git 仓库；不要上传患者身份、未公开专利核心、审稿材料或保密数据到远程模型。

---

## 七、配置学术数据源（可选，提高检索质量）

在启动前设置以下环境变量，可以显著提高搜索结果的数量和质量：

```bash
# Crossref —— 只需填邮箱，免费，强烈推荐
export CROSSREF_EMAIL=你的邮箱@university.edu

# PubMed / NCBI —— 生物医学领域推荐
export NCBI_EMAIL=你的邮箱@university.edu
export NCBI_API_KEY=你的密钥      # 可选，有密钥请求速率更高

# Semantic Scholar —— 可选
export SEMANTIC_SCHOLAR_API_KEY=你的密钥

# OpenAlex —— 可选
export OPENALEX_API_KEY=你的密钥

# Web of Science —— 需要机构授权
export WOS_API_KEY=你的Clarivate密钥
```

**即使什么都不配置，也可以正常使用基础检索功能。** 其中 `CROSSREF_EMAIL` 最容易配置——只需要一个邮箱地址即可获得更稳定的检索结果。

---

## 八、使用 .env 文件管理配置（推荐）

如果不想每次启动都手动输入环境变量，可以使用配置文件：

```bash
# 从示例文件复制
cp .env.example .env
```

然后用任意文本编辑器（如 VS Code、记事本等）打开 `.env` 文件，按需修改。常用配置项参考：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `LATTICE_HOST` | 监听地址 | `127.0.0.1` |
| `LATTICE_PORT` | 监听端口 | `8765` |
| `LATTICE_AUTH_MODE` | 认证模式（`accounts`/`open`/`shared`） | `accounts` |
| `LATTICE_PDF_ENGINE` | PDF 解析引擎（`core`/`pymupdf`） | `core` |
| `LATTICE_LLM_PROVIDER` | LLM 服务商 | `none` |
| `LATTICE_ALLOW_REMOTE_LLM` | 是否允许远程模型 | `false` |
| `CROSSREF_EMAIL` | Crossref 联系邮箱 | 空 |

> **注意**：`.env` 文件包含密钥等敏感信息，已被 `.gitignore` 排除，不会被提交到 Git 仓库。

---

## 九、高级 PDF 解析（可选）

默认的 `core` 引擎使用 PDFPlumber，适合大部分带文字层的论文 PDF。如果你需要更强的版面识别和本机 OCR 能力：

```bash
# 安装高级 PDF 引擎
pip install -e ".[advanced-pdf]"

# 启动时指定引擎
export LATTICE_PDF_ENGINE=pymupdf
latticescholar
```

> **许可证提醒**：高级引擎中的 PyMuPDF / PyMuPDF4LLM 采用 AGPL 或 Artifex 商业许可，并非本项目 Apache-2.0 许可的一部分。公网托管、闭源修改或商业使用前，请自行确认许可义务。

---

## 十、日常使用：停止与再次启动

### 停止服务

在运行 `latticescholar` 的终端窗口中按 **`Ctrl + C`**。

### 再次启动（已安装过的情况下）

**macOS / Linux：**

```bash
cd LatticeScholar
source .venv/bin/activate
latticescholar
```

**Windows PowerShell：**

```powershell
cd LatticeScholar
.venv\Scripts\Activate.ps1
latticescholar
```

**Windows CMD：**

```cmd
cd LatticeScholar
.venv\Scripts\activate.bat
latticescholar
```

不需要再次执行 `pip install`，除非项目版本更新了。

---

## 十一、更新到最新版本

### 使用 Git 克隆的用户

```bash
cd LatticeScholar

# 拉取最新代码
git pull origin main

# 激活虚拟环境
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell

# 重新安装（更新依赖）
pip install -e .

# 启动
latticescholar
```

### 使用 ZIP 下载的用户

1. 重新下载最新的 ZIP 包
2. 解压覆盖到同一位置
3. 重新激活虚拟环境并执行 `pip install -e .`

### Docker 用户

```bash
cd LatticeScholar
git pull origin main
docker compose up -d --build
```

---

## 十二、常见问题

| 问题 | 解决方法 |
|---|---|
| `python3` 命令找不到 | 安装 Python 3.9+，Windows 上尝试用 `py` 或 `python` 代替 |
| `pip install` 报错 | 确认 Python 版本 >= 3.9；确认虚拟环境已激活（终端行首应显示 `(.venv)`） |
| 浏览器没有自动打开 | 手动在浏览器中访问 http://127.0.0.1:8765 |
| Windows 无法运行 `.ps1` 脚本 | 执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后重试 |
| 端口 8765 被其他程序占用 | 使用 `latticescholar --port 8766` 换一个端口 |
| 不想自动打开浏览器 | 使用 `latticescholar --no-browser` |
| 检索结果较少 | 配置 `CROSSREF_EMAIL` 邮箱；添加更多学术数据源 API Key |
| PDF 解析效果差 | 确认 PDF 有文字层（非纯扫描件）；扫描件需先用外部工具做 OCR |
| 模型连接测试失败 | 检查 API Key 是否正确；检查 Base URL 和模型名称是否与厂商控制台一致 |
| macOS 双击 `.command` 文件提示无法打开 | 右键点击 → 打开 → 确认；或在终端执行 `chmod +x "启动 LatticeScholar.command"` |
| `git pull` 提示冲突 | 如果只修改了 `.env` 文件，不会冲突（已被 gitignore）；其他冲突可用 `git stash && git pull && git stash pop` |

---

## 十三、命令速查表

```bash
# ============ 首次安装 ============
git clone https://github.com/CBarran498/LatticeScholar.git
cd LatticeScholar
python3 -m venv .venv
source .venv/bin/activate            # macOS/Linux
pip install -e .
latticescholar

# ============ 日常启动 ============
cd LatticeScholar
source .venv/bin/activate            # macOS/Linux
latticescholar

# ============ 更新代码 ============
cd LatticeScholar
git pull origin main
source .venv/bin/activate
pip install -e .
latticescholar

# ============ 可选参数 ============
latticescholar --port 9000           # 指定端口
latticescholar --no-browser          # 不自动打开浏览器
latticescholar --host 0.0.0.0        # 局域网内其他设备访问

# ============ 开发与测试 ============
pip install -e ".[dev]"              # 安装开发依赖
pytest -q                            # 运行测试
ruff check .                         # 代码检查

# ============ Docker ============
docker compose up -d --build         # 构建并启动
docker compose down                  # 停止
docker compose logs -f               # 查看日志
```
