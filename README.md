# 🔥 MediaCrawler - 自媒体平台爬虫 🕷️


## 📖 项目简介

一个功能强大的**多平台自媒体数据采集工具**，支持小红书、抖音、快手、B站、微博、贴吧、知乎等主流平台的公开信息抓取。

### 🔧 技术原理

- **核心技术**：基于 [Playwright](https://playwright.dev/) 浏览器自动化框架登录保存登录态
- **无需JS逆向**：利用保留登录态的浏览器上下文环境，通过 JS 表达式获取签名参数
- **优势特点**：无需逆向复杂的加密算法，大幅降低技术门槛


## ✨ 功能特性
| 平台   | 关键词搜索 | 指定帖子ID爬取 | 二级评论 | 指定创作者主页 | 登录态缓存 | IP代理池 | 生成评论词云图 |
| ------ | ---------- | -------------- | -------- | -------------- | ---------- | -------- | -------------- |
| 小红书 | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 抖音   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 快手   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| B 站   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 微博   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 贴吧   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 知乎   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |



<strong>MediaCrawlerPro 重磅发布！开源不易，欢迎订阅支持</strong>

> 专注于学习成熟项目的架构设计，不仅仅是爬虫技术，Pro 版本的代码设计思路同样值得深入学习！

[MediaCrawlerPro](https://github.com/MediaCrawlerPro) 相较于开源版本的核心优势：

#### 🎯 核心功能升级
- ✅ **自媒体内容拆解Agent**（新增功能）
- ✅ **断点续爬功能**（重点特性）
- ✅ **多账号 + IP代理池支持**（重点特性）
- ✅ **去除 Playwright 依赖**，使用更简单
- ✅ **完整 Linux 环境支持**

#### 🏗️ 架构设计优化
- ✅ **代码重构优化**，更易读易维护（解耦 JS 签名逻辑）
- ✅ **企业级代码质量**，适合构建大型爬虫项目
- ✅ **完美架构设计**，高扩展性，源码学习价值更大

#### 🎁 额外功能
- ✅ **自媒体视频下载器桌面端**（适合学习全栈开发）
- ✅ **多平台首页信息流推荐**（HomeFeed）
- ✅ **AI Agent Skill 支持**（[OpenClaw](https://openclaw.ai/) 🦞 / Claude Code / Cursor 一键安装，让 Agent 自动爬取数据）
- [ ] **基于评论分析AI Agent正在开发中 🚀🚀**

点击查看：[MediaCrawlerPro 项目主页](https://github.com/MediaCrawlerPro) 更多介绍



## 🚀 快速开始

> 💡 **如果这个项目对您有帮助，请给个 ⭐ Star 支持一下！**

## 📋 前置依赖

### 🚀 uv 安装（推荐）

在进行下一步操作之前，请确保电脑上已经安装了 uv：

- **安装地址**：[uv 官方安装指南](https://docs.astral.sh/uv/getting-started/installation)
- **验证安装**：终端输入命令 `uv --version`，如果正常显示版本号，证明已经安装成功
- **推荐理由**：uv 是目前最强的 Python 包管理工具，速度快、依赖解析准确

### 🟢 Node.js 安装

项目依赖 Node.js，请前往官网下载安装：

- **下载地址**：https://nodejs.org/en/download/
- **版本要求**：>= 16.0.0

### 📦 Python 包安装

```shell
# 进入项目目录
cd MediaCrawler

# 使用 uv sync 命令来保证 python 版本和相关依赖包的一致性
uv sync
```

### 🌐 浏览器驱动安装（可选）

> 如果使用默认的 CDP 模式（连接已有 Chrome 浏览器），**无需安装浏览器驱动**。仅在使用标准 Playwright 模式时需要安装。

```shell
# 仅在标准 Playwright 模式下需要安装浏览器驱动
uv run playwright install
```

### 🌍 Chrome 浏览器配置（推荐）

项目默认使用 CDP 模式连接用户已有的 Chrome 浏览器，可以复用浏览器已有的登录状态、Cookie、扩展等，**大幅降低平台风控检测风险**。

使用前需要：

1. **安装最新版 Chrome 浏览器**（版本 >= 144），[下载地址](https://www.google.com/chrome/)
2. **开启远程调试功能**：在 Chrome 地址栏输入 `chrome://inspect/#remote-debugging`，勾选 **"Allow remote debugging for this browser instance"**
3. 页面显示 `Server running at: 127.0.0.1:9222` 表示已就绪

> 💡 **提示**：运行爬虫后，Chrome 浏览器会弹出确认对话框，点击"接受"即可。程序会等待用户确认，60秒内操作完成即可。
>
> 如果不想使用 CDP 模式，可以在 `config/base_config.py` 中设置 `ENABLE_CDP_MODE = False` 切换为标准 Playwright 模式。

## 🚀 运行爬虫程序

```shell
# 在 config/base_config.py 查看配置项目功能，写的有中文注释

# 从配置文件中读取关键词搜索相关的帖子并爬取帖子信息与评论
uv run main.py --platform xhs --lt qrcode --type search

# 从配置文件中读取指定的帖子ID列表获取指定帖子的信息与评论信息
uv run main.py --platform xhs --lt qrcode --type detail

# 打开对应APP扫二维码登录

# 其他平台爬虫使用示例，执行下面的命令查看
uv run main.py --help
```

<details>
<summary>🖥️ <strong>WebUI 可视化操作界面</strong></summary>

MediaCrawler 提供了基于 Web 的可视化操作界面，无需命令行也能轻松使用爬虫功能。

#### 启动 WebUI 服务

```shell
# 启动 API 服务器（默认端口 8080）
uv run uvicorn api.main:app --port 8080 --reload

# 或者使用模块方式启动
uv run python -m api.main
```

启动成功后，访问 `http://localhost:8080` 即可打开 WebUI 界面。

#### WebUI 功能特性

- 可视化配置爬虫参数（平台、登录方式、爬取类型等）
- 实时查看爬虫运行状态和日志
- 数据预览和导出

#### 界面预览

<img src="docs/static/images/img_8.png" alt="WebUI 界面预览">

</details>

<details>
<summary>🔗 <strong>使用 Python 原生 venv 管理环境（不推荐）</strong></summary>

#### 创建并激活 Python 虚拟环境

> 如果是爬取抖音和知乎，需要提前安装 nodejs 环境，版本大于等于：`16` 即可

```shell
# 进入项目根目录
cd MediaCrawler

# 创建虚拟环境
# 我的 python 版本是：3.11 requirements.txt 中的库是基于这个版本的
# 如果是其他 python 版本，可能 requirements.txt 中的库不兼容，需自行解决
python -m venv venv

# macOS & Linux 激活虚拟环境
source venv/bin/activate

# Windows 激活虚拟环境
venv\Scripts\activate
```

#### 安装依赖库

```shell
pip install -r requirements.txt
```

#### 安装 playwright 浏览器驱动

```shell
playwright install
```

#### 运行爬虫程序（原生环境）

```shell
# 项目默认是没有开启评论爬取模式，如需评论请在 config/base_config.py 中的 ENABLE_GET_COMMENTS 变量修改
# 一些其他支持项，也可以在 config/base_config.py 查看功能，写的有中文注释

# 从配置文件中读取关键词搜索相关的帖子并爬取帖子信息与评论
python main.py --platform xhs --lt qrcode --type search

# 从配置文件中读取指定的帖子ID列表获取指定帖子的信息与评论信息
python main.py --platform xhs --lt qrcode --type detail

# 打开对应APP扫二维码登录

# 其他平台爬虫使用示例，执行下面的命令查看
python main.py --help
```

</details>


## 💾 数据保存

MediaCrawler 支持多种数据存储方式，包括 CSV、JSON、JSONL、Excel、SQLite 和 MySQL 数据库。

📖 **详细使用说明请查看：[数据存储指南](docs/data_storage_guide.md)**