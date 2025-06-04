# TG Monitor

基于 Python + Telethon + Streamlit 的 Telegram 频道消息监控与管理系统。

## 功能简介

- 自动监听指定 Telegram 频道消息，只保存包含网盘链接的消息
- Web 界面可视化浏览和筛选消息
- 支持频道管理、消息去重、标签修复等维护功能
- 支持 systemd/定时任务后台运行，日志可查

## 快速部署

### 1. 克隆项目并安装依赖

```bash
git clone <你的仓库地址>
cd tg-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置数据库

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y
sudo -u postgres psql
# 在 psql 命令行中执行：
CREATE DATABASE tg_monitor;
CREATE USER tg_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tg_monitor TO tg_user;
\q
```

### 3. 配置环境变量

编辑 `.env` 文件，示例：

```
TELEGRAM_API_ID=你的API_ID
TELEGRAM_API_HASH=你的API_HASH
DATABASE_URL=postgresql://tg_user:your_password@localhost:5432/tg_monitor
DEFAULT_CHANNELS=频道1,频道2
LOG_LEVEL=INFO
```

### 4. 初始化数据库表

```bash
python init_db.py
```

### 5. 启动服务

- 监控服务（后台运行）
  ```bash
  nohup python monitor.py > data/monitor.log 2>&1 &
  ```
- Web 服务（后台运行）
  ```bash
  nohup streamlit run web.py > data/web.log 2>&1 &
  ```

### 6. 管理维护命令

```bash
python manage.py --list-channels                # 查看频道列表
python manage.py --add-channel 频道名           # 添加频道
python manage.py --del-channel 频道名           # 删除频道
python manage.py --edit-channel 旧频道名 新频道名  # 修改频道名
python manage.py --fix-tags                     # 修复tags脏数据
python manage.py --dedup-links                  # 网盘链接去重
```

## 其他说明

- 支持 systemd 服务和定时任务，详见文档或源码注释。
- 日志、会话等文件统一放在 `data/` 目录，便于管理。
- 代码结构清晰，易于二次开发和维护。

如需详细文档或遇到问题，欢迎提 issue 或 PR！
