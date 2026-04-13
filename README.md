# TG Monitor

基于 Python、Telethon、FastAPI、React 和 PostgreSQL 的 Telegram 频道监控系统。

当前仓库已经完成从旧版 Streamlit 页面到 `FastAPI + React/Vite` 架构的迁移：

- `app/core/monitor.py` 负责监听 Telegram 频道并写库
- `app/api/main.py` 提供后端 API
- `frontend/` 提供 React 前端
- `docker/` 和 `DEPLOY.md` 分别覆盖容器化与非 Docker 部署

旧的 Streamlit 前端已弃用，不再作为当前部署方案的一部分。

## 主要功能

- 监听 Telegram 频道消息并自动入库
- 解析阿里云盘、百度网盘、夸克、天翼、115、123、UC、迅雷等主流网盘链接
- 提供消息列表、搜索、筛选、分页、统计、后台管理等功能
- 支持频道管理、链接去重、链接巡检、游客模式等运维能力

## 项目结构

```text
tg/
├── app/
│   ├── api/          # FastAPI 路由
│   ├── core/         # Telegram 监控与解析逻辑
│   ├── models/       # 数据库模型与配置
│   ├── schemas/      # API 数据结构
│   ├── scripts/      # 初始化与管理脚本
│   └── services/     # 业务服务层
├── frontend/         # React + TypeScript + Vite 前端
├── docker/           # Dockerfile 与 docker compose
├── data/             # 本地数据目录
├── DEPLOY.md         # 当前推荐的生产部署文档
└── 网盘资源电报频道监控.md
```

## 环境要求

- Python 3.10 或 3.11
- Node.js 18+
- PostgreSQL 13 / 14 / 15

## 环境变量

根目录 `.env` 至少需要这些配置：

```env
TELEGRAM_API_ID=你的 Telegram API ID
TELEGRAM_API_HASH=你的 Telegram API HASH
DATABASE_URL=postgresql://tg_user:password@127.0.0.1:5432/tg_monitor
DATABASE_URL_ASYNC=postgresql+asyncpg://tg_user:password@127.0.0.1:5432/tg_monitor
DEFAULT_CHANNELS=channel_a,channel_b
SECRET_SALT=请替换成随机长字符串
LOG_LEVEL=INFO
FRONTEND_URL=http://localhost:3000
PUBLIC_DASHBOARD_ENABLED=false
```

说明：

- `DATABASE_URL_ASYNC` 不填时，程序会基于 `DATABASE_URL` 自动推导
- 生产环境如果前端走反代域名，需要把 `FRONTEND_URL` 改成真实访问地址
- `PUBLIC_DASHBOARD_ENABLED=true` 时可开启游客面板

## 快速开始

### 1. 安装后端依赖

```bash
python -m venv tgmonitor-venv
source tgmonitor-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv tgmonitor-venv
.\tgmonitor-venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 初始化数据库和默认用户

```bash
python -m app.scripts.init_db
```

这一步会：

- 创建数据库表
- 按 `DEFAULT_CHANNELS` 初始化频道
- 在 `users.json` 不存在时创建默认管理员

默认管理员：

- 用户名：`admin`
- 密码：`admin123`

首次登录后请立即修改密码。

### 3. 首次 Telegram 登录

直接运行监控程序完成 Telethon 登录：

```bash
python -m app.core.monitor
```

首次运行会提示输入手机号、验证码，成功后会在项目根目录生成：

```text
tg_monitor_session.session
```

后续同一环境通常不需要重复登录。

### 4. 启动后端 API

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

可访问：

- API 根路径：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/api/health`
- Swagger：`http://127.0.0.1:8000/api/docs`

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：

- 前端：`http://localhost:3000`

Vite 开发环境会把 `/api` 请求代理到本地后端。

### 6. 启动监控服务

开发阶段建议单独开一个终端运行：

```bash
python -m app.core.monitor
```

这样可以实时查看频道监听、解析、入库日志。

## 常用管理命令

```bash
python -m app.scripts.manage --list-channels
python -m app.scripts.manage --add-channel channel_a channel_b
python -m app.scripts.manage --del-channel channel_a
python -m app.scripts.manage --edit-channel old_name new_name
python -m app.scripts.manage --dedup-links
python -m app.scripts.manage --dedup-links-fast
python -m app.scripts.manage --check-links 24 5
python -m app.scripts.manage --link-stats
python -m app.scripts.manage --show-invalid-links
python -m app.scripts.manage --help
```

用户管理：

```bash
python -m app.scripts.init_users --create-default
python -m app.scripts.init_users --list-users
python -m app.scripts.init_users --add-user username password
python -m app.scripts.init_users --change-password username new_password
python -m app.scripts.init_users --remove-user username
```

## 部署说明

当前推荐做法：

- 非 Docker 生产部署：看 `DEPLOY.md`
- Docker / Compose：看 `docker/docker-compose.yml`
- 转存中心详细使用说明：看 `docs/转存中心使用说明.md`

`DEPLOY.md` 已按当前项目形态维护，核心是：

- FastAPI 后端运行在 `8000`
- React 前端构建后交给 Nginx 托管
- 反代统一把 `/api` 指向后端
- 监控进程与 API 进程分开托管

## 说明

- 根目录 `网盘资源电报频道监控.md` 是中文介绍文档
- `frontend/README.md` 只负责前端局部说明
- 如果你在老文章或旧提交里看到 `streamlit run app/web/web.py`，那已经不是当前项目的启动方式
