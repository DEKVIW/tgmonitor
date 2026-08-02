# TG Monitor

TG Monitor 是一个面向 Telegram 频道资源监控、网盘链接治理和资源转存运营的 Web 管理系统。项目当前已经迁移到 `FastAPI + React/Vite + PostgreSQL` 架构，日常使用以浏览器 UI 为主，旧版 Streamlit 页面不再作为当前部署方案的一部分。

## 当前形态

- 后端：FastAPI 提供 API，SQLAlchemy 访问 PostgreSQL
- 前端：React + TypeScript + Vite，提供完整后台界面
- 监听：Telethon 持续监听 Telegram 频道消息并入库
- Worker：处理链接巡检、转存队列、追更任务、发布规则和日志清理
- 部署：支持本机 systemd 服务，也保留 Docker / Compose 配置

日常管理一般不需要再跑管理命令，频道管理、链接检查、AI 配置、资源运营、转存任务、备份和系统设置都已经在 UI 中完成。命令主要用于首次初始化、开发启动、服务部署、备份恢复和故障排查。

## 主要功能

- Telegram 频道消息监听、解析、搜索、筛选、分页和详情查看
- 支持阿里云盘、百度网盘、夸克、天翼、115、123、UC、迅雷等主流网盘链接解析
- 游客公开面板、登录入口、管理员后台和访问权限控制
- 统计信息、数据分析、趋势图和资源分布概览
- 频道管理、系统配置、账号策略、并发限制和安全配置
- 链接去重、链接巡检、失效检测、批量维护和运行日志查看
- AI 中心：AI 提供方、模型路由、识别任务和业务场景配置
- 资源运营：资源识别、候选资源、工作台、价值判断和人工复核
- 转存中心：网盘账号、手动转存、批次队列、转存日志、发布记录和发布规则
- 追更任务：自动增量检查、候选判断、文件诊断、目录复用、原链/新链状态检查
- 备份管理：数据库备份、恢复入口和备份文件管理
- 后台 Worker 自动执行任务队列，并定期清理转存/AI 执行日志

## 项目结构

```text
tg/
├── app/
│   ├── api/              # FastAPI 路由和运行时接口
│   ├── core/             # Telegram 监听与消息解析
│   ├── models/           # 数据库模型与配置模型
│   ├── schemas/          # API 请求/响应结构
│   ├── scripts/          # 初始化、用户、迁移和运维脚本
│   ├── services/         # 业务服务层
│   │   ├── ai_center/    # AI 提供方、模型与路由
│   │   ├── link_check/   # 链接解析、检测与缓存
│   │   ├── pan_transfer/ # 转存中心、追更、发布和队列
│   │   ├── resource_identity/ # 资源身份识别
│   │   └── resource_ops/ # 资源运营工作台
│   ├── utils/            # 通用工具
│   └── worker/           # 后台任务入口
├── frontend/
│   ├── src/api/          # 前端 API 封装
│   ├── src/components/   # 页面组件和业务组件
│   ├── src/pages/        # Dashboard、AI 中心、资源运营等页面
│   ├── src/store/        # 前端状态
│   └── src/types/        # TypeScript 类型
├── docker/               # Dockerfile、Compose 和 Nginx 配置
├── scripts/              # systemd 服务、备份和恢复脚本
├── tests/                # 后端测试
└── data/                 # 本地运行数据目录
```

## 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+
- 可访问 Telegram 的网络环境

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
- `PUBLIC_DASHBOARD_ENABLED=true` 时可以开启游客公开面板

## 快速开始

### 0. 启动数据库

项目依赖 PostgreSQL。初始化数据库、启动 API、启动监听和 Worker 之前，都需要先确保 PostgreSQL 已启动，并且 `.env` 中的 `DATABASE_URL` 可以连接成功。

常见检查方式：

```bash
pg_isready -h 127.0.0.1 -p 5432
```

如果使用 `docker/docker-compose.yml`，PostgreSQL 会由其中的 `db` 服务启动；如果使用 systemd 或手动部署，需要先安装并启动宿主机上的 PostgreSQL。

### 1. 安装后端依赖

Linux / macOS:

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

### 2. 初始化数据库和账号引导

```bash
python -m app.scripts.init_db
```

首次初始化会创建数据库表，并写入默认频道。当前运行时账号以数据库表 `user_accounts` 和 `auth_identities` 为准。

API 启动时会执行账号存储引导：

- 如果数据库里已有账号，直接使用数据库账号
- 如果数据库为空但存在旧版 `users.json`，会把旧用户迁移到数据库
- 如果数据库为空且没有旧用户，才会创建默认管理员

空库默认管理员：

- 用户名：`admin`
- 密码：`admin123`

首次登录后请立即在 UI 中修改密码。当前版本不再把 `users.json` 作为主要账号存储，它只作为旧版本迁移来源保留兼容。

### 3. 完成 Telegram Session 登录

首次运行监听程序会触发 Telethon 登录：

```bash
python -m app.core.monitor
```

按提示输入手机号、验证码后，会在项目根目录生成：

```text
tg_monitor_session.session
```

同一部署环境通常只需要登录一次。

### 4. 启动后端 API

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

常用入口：

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

### 6. 启动监听和后台 Worker

开发阶段可以分别开终端运行：

```bash
python -m app.core.monitor
python -m app.worker.main
```

生产环境建议使用 `scripts/tg-api.service`、`scripts/tg-monitor.service`、`scripts/tg-worker.service` 托管三个进程。

## UI 页面

- `/`：游客公开面板，是否开放由系统配置控制
- `/dashboard`：消息列表、搜索、筛选和资源查看
- `/statistics`：基础统计信息
- `/analytics`：管理员数据分析
- `/ai-center`：AI 中心和模型路由
- `/resource-ops`：资源运营与转存中心
- `/backups`：备份管理
- `/admin`：后台管理、频道、系统和安全配置

## 命令使用边界

当前项目已经以 UI 管理为主，下面这些命令只作为补充：

- 首次初始化：`python -m app.scripts.init_db`
- 首次 Telegram 登录：`python -m app.core.monitor`
- 开发启动：`uvicorn`、`npm run dev`
- 生产托管：`systemctl restart tg-api tg-monitor tg-worker`
- 备份恢复：`scripts/backup_db.sh`、`scripts/restore_db.sh`
- 故障排查：`journalctl`、`curl`、`python -m app.scripts.manage --help`

频道、用户、链接检查、AI、转存、追更和资源运营等日常操作优先在 Web UI 中完成。

## 部署说明

非 Docker 部署的核心进程：

- `tg-api`：FastAPI 后端，默认监听 `8000`
- `tg-monitor`：Telegram 监听服务
- `tg-worker`：后台任务队列、链接巡检、转存和日志清理

前端生产构建：

```bash
cd frontend
npm install
npm run build
```

构建产物位于 `frontend/dist`，通常交给 Nginx 托管，并把 `/api` 反向代理到后端 API。

Docker 部署可以参考 `docker/docker-compose.yml`，前端容器内的 Nginx 配置在 `docker/nginx.conf`。如果使用外层 Nginx 托管前端并反代后端 API，可以参考 `docker/nginx_proxy/conf.d/tg-monitor.example.conf`。

## 说明

- 旧版 Streamlit 启动方式已经弃用
- 前端构建产物、测试缓存和会话文件默认不纳入 Git
- 生产环境请妥善保存 `.env`、`tg_monitor_session.session` 和数据库备份
