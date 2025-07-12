# TG Monitor

基于 Python + Telethon + Streamlit 的 Telegram 频道消息监控与管理系统。

- 自动监听**网盘影视资源分享**类 Telegram 频道，只保存包含网盘链接的消息
- 支持主流网盘类型：**阿里云盘、百度网盘、夸克网盘、天翼云盘、115 网盘、123 云盘、UC 网盘、迅雷** 
- 推荐/适配频道（可自定义扩展）：

| 频道名         | 频道名        | 频道名           | 频道名   |
| -------------- | ------------- | ---------------- | -------- |
| BaiduCloudDisk | tianyirigeng  | Aliyun_4K_Movies | NewQuark |
| XiangxiuNB     | shareAliyun   | bdwpzhpd         | Lsp115   |
| tyypzhpd       | SharePanBaidu | QuarkFree        | alyp_1   |
| vip115hot      | QukanMovie    |                  |          |

- Web 界面可视化浏览和筛选消息，支持频道管理、消息去重、标签修复等维护功能

## 环境与依赖版本建议

- **推荐 Python 版本**：3.10 或 3.11（3.12 也可，优先用 3.10/3.11，兼容性最佳）
- **推荐 PostgreSQL 版本**：13、14 或 15
- **依赖安装**：已在 requirements.txt 中声明，`pip install -r requirements.txt` 一键安装。

## 首次 Telethon 登录

**方法一：推荐 - 使用 session 获取脚本**

1. 运行专门的 session 获取脚本：

   ```bash
   python get_session.py
   ```

2. 按提示输入 API 凭据：

   - **TELEGRAM_API_ID**：你的 Telegram API ID
   - **TELEGRAM_API_HASH**：你的 Telegram API Hash

3. 按提示输入手机号、验证码

   - **手机号格式**：`+国家代码手机号`（如：`+8613812345678`）

4. 登录成功后，session 文件会自动保存为 `tg_monitor_session.session`

**方法二：直接运行监控服务登录**

1. 本地运行监控服务进行登录：

   ```bash
   python -m app.core.monitor
   ```

2. 按提示输入手机号、验证码

3. 登录成功后，session 文件会自动保存为 `tg_monitor_session.session`

**Session 文件说明**：

- 文件名：`tg_monitor_session.session`
- 包含 Telegram 登录凭据，无需重复登录
- 请妥善保管，不要泄露给他人
- 如果 session 失效，删除文件重新登录即可

---

## Docker 部署说明

### 1. 克隆项目

```
git clone https://github.com/DEKVIW/tgmonitor.git
cd docker
```

### 2. 环境准备

.env 环境配置：

```
TELEGRAM_API_ID=你的API_ID
TELEGRAM_API_HASH=你的API_HASH
DATABASE_URL=postgresql://tg_user:password@db:5432/tg_monitor
DEFAULT_CHANNELS=频道1,频道2
LOG_LEVEL=INFO
SECRET_SALT=your_secret_salt_key_here
```

**⚠️ 重要提示：**

1. **SECRET_SALT 密钥**：用于用户登录验证，建议使用随机生成的强密钥

   - 可以使用项目提供的脚本生成：`python generate_secret.py`
   - 可以使用在线工具生成：https://www.random.org/strings/
   - 或使用命令生成：`openssl rand -hex 32`
   - 示例：`SECRET_SALT=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234`

2. **数据库密码包含特殊字符时的转义处理**

如果数据库密码包含特殊字符（如 `#`、`@`、`%`、`&`、`+`、`=`、`!`、`$`、`*`、`(`、`)`、`[`、`]`、`{`、`}`、`|`、`\`、`:`、`;`、`"`、`'`、`<`、`>`、`,`、`/`、`?`），需要进行 URL 编码转义。**在线 URL 编码工具**：[Online URL Encoder](https://www.url-encode-decode.com/)

**示例**：

- 原始密码：`1j7wxLn#ZTlNZ#3tpkwF`
- 转义后：`1j7wxLn%23ZTlNZ%233tpkwF`（`#` 转义为 `%23`）

**完整示例**：

```
# 原始密码：1j7wxLn#ZTlNZ#3tpkwF
DATABASE_URL=postgresql://tg_user:1j7wxLn%23ZTlNZ%233tpkwF@localhost:5432/tg_monitor
SECRET_SALT=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234
```

### 3. 构建与初始化数据库

```bash
cd docker
docker-compose up -d db
docker-compose run --rm monitor python -m app.scripts.init_db
```

**注意**: 此命令会自动创建默认管理员用户（用户名: admin，密码: admin123）

### 4. 用户管理（可选）

如果需要创建其他用户或修改用户信息：

```bash
# 创建默认用户（如果还没有）
docker-compose run --rm monitor python -m app.scripts.init_users --create-default

# 添加新用户
docker-compose run --rm monitor python -m app.scripts.init_users --add-user 用户名 密码 [姓名] [邮箱]

# 修改密码
docker-compose run --rm monitor python -m app.scripts.init_users --change-password 用户名 新密码

# 修改用户名
docker-compose run --rm monitor python -m app.scripts.init_users --change-username 旧用户名 新用户名

# 编辑用户信息
docker-compose run --rm monitor python -m app.scripts.init_users --edit-user 用户名 [姓名] [邮箱]

# 查看所有用户
docker-compose run --rm monitor python -m app.scripts.init_users --list-users

#删除用户
docker-compose run --rm monitor python -m app.scripts.init_users --delete-user 用户名
```

注意操作后服务需要重启：

### 5. 启动服务

```bash
docker-compose up -d
```

- 监控服务和 Web 服务会自动启动
- Web 界面访问：http://localhost:8501

**查看服务状态和日志**：

```bash
# 查看服务状态
docker-compose ps

# 查看监控服务日志
docker-compose logs -f monitor

# 查看Web服务日志
docker-compose logs -f web

# 查看数据库日志
docker-compose logs -f db
```

### 6. 管理脚本用法

```bash
docker-compose run --rm monitor python -m app.scripts.manage --list-channels #列出频道
docker-compose run --rm monitor python -m app.scripts.manage --add-channel #添加频道（多个用空格分隔）
docker-compose run --rm monitor python -m app.scripts.manage --dedup-links #链接去重
```

### 7. 其它注意事项

- `.env` 文件中的 `DATABASE_URL` 主机名应为 `db`，如：
  ```
  DATABASE_URL=postgresql://tg_user:password@db:5432/tg_monitor
  ```
  
- 管理脚本、初始化等操作都建议用 `docker-compose run --rm ...` 方式临时运行

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/DEKVIW/tgmonitor.git
cd tgmonitor
```

### 2. 配置数据库（系统环境）

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

### 3. 创建虚拟环境并安装依赖

```bash
python3 -m venv tgmonitor-venv
source tgmonitor-venv/bin/activate
pip install -r requirements.txt
```

### 4. 配置环境变量

编辑 `.env` 文件，示例：

```
TELEGRAM_API_ID=你的API_ID
TELEGRAM_API_HASH=你的API_HASH
DATABASE_URL=postgresql://tg_user:your_password@localhost:5432/tg_monitor
DEFAULT_CHANNELS=频道1,频道2
LOG_LEVEL=INFO
SECRET_SALT=your_secret_salt_key_here
```

### 5. 初始化数据库表

```bash
python -m app.scripts.init_db
```

**注意**: 此命令会自动创建默认管理员用户（用户名: admin，密码: admin123）

### 6. 用户管理（可选）

如果需要创建其他用户或修改用户信息：

```bash
# 创建默认用户（如果还没有）
python -m app.scripts.init_users --create-default

# 添加新用户
python -m app.scripts.init_users --add-user 用户名 密码 [姓名] [邮箱]

# 修改密码
python -m app.scripts.init_users --change-password 用户名 新密码

# 修改用户名
python -m app.scripts.init_users --change-username 旧用户名 新用户名

# 编辑用户信息
python -m app.scripts.init_users --edit-user 用户名 [姓名] [邮箱]

# 查看所有用户
python -m app.scripts.init_users --list-users
```

### 7. 启动服务

**第一步：前台测试运行**

先正常启动服务进行测试，确认稳定后再后台运行：

```bash
# 启动监控服务（前台运行，用于测试）
python -m app.core.monitor

# 新开一个终端，启动Web服务（前台运行，用于测试）
streamlit run app/web/web.py
```

**测试要点**：

- 监控服务：检查是否正常连接 Telegram，是否开始监听频道
- Web 服务：访问 http://localhost:8501 检查登录和功能是否正常
- 观察日志输出，确认无错误信息

**第二步：后台稳定运行**

测试稳定后，使用后台运行：

```bash
# 监控服务（后台运行）
nohup python -m app.core.monitor > data/monitor.log 2>&1 &

# Web服务（后台运行）
nohup streamlit run app/web/web.py > data/web.log 2>&1 &
```

**查看运行状态**：

```bash
# 查看进程
ps aux | grep python

# 查看日志
tail -f data/monitor.log
tail -f data/web.log
```

### 8. 管理维护命令

```bash
python -m app.scripts.manage --list-channels                # 查看频道列表
python -m app.scripts.manage --add-channel 频道名           # 添加频道
python -m app.scripts.manage --del-channel 频道名           # 删除频道
python -m app.scripts.manage --edit-channel 旧频道名 新频道名  # 修改频道名
python -m app.scripts.manage --fix-tags                     # 修复tags脏数据
python -m app.scripts.manage --dedup-links                  # 网盘链接去重
```

**用户管理命令**：

```bash
python -m app.scripts.init_users --create-default           # 创建默认用户
python -m app.scripts.init_users --add-user 用户名 密码     # 添加用户
python -m app.scripts.init_users --change-password 用户名 新密码  # 修改密码
python -m app.scripts.init_users --change-username 旧用户名 新用户名  # 修改用户名
python -m app.scripts.init_users --edit-user 用户名 [姓名] [邮箱]  # 编辑用户信息
python -m app.scripts.init_users --list-users              # 查看所有用户
```

**查看帮助**: `python -m app.scripts.manage --help

## 链接检测功能使用说明

链接检测系统可以检测数据库中各种网盘链接的有效性，支持多种检测方式、时间段选择、中断恢复、详细统计报告和数据管理功能。

### 快速上手

```bash
# 1. 首次使用 - 小规模测试
python -m app.scripts.manage --check-links 1 3

# 2. 扩大范围 - 检测最近24小时
python -m app.scripts.manage --check-links 24 5

# 3. 查看结果
python -m app.scripts.manage --link-stats
python -m app.scripts.manage --show-invalid-links
```

### 基础检测命令

```bash
# 检测最近N小时的链接
python -m app.scripts.manage --check-links                    # 最近24小时 (默认5并发)
python -m app.scripts.manage --check-links 48                 # 最近48小时
python -m app.scripts.manage --check-links 24 10              # 最近24小时，10并发

# 检测所有历史链接
python -m app.scripts.manage --check-all-links                # 默认5并发
python -m app.scripts.manage --check-all-links 10             # 10并发
```

### 时间段检测命令

```bash
# 预定义时间段
python -m app.scripts.manage --check-period today             # 今天
python -m app.scripts.manage --check-period yesterday         # 昨天
python -m app.scripts.manage --check-period week              # 最近7天
python -m app.scripts.manage --check-period month             # 最近30天
python -m app.scripts.manage --check-period year              # 最近365天

# 指定时间检测
python -m app.scripts.manage --check-period 2024-01-15        # 指定日期
python -m app.scripts.manage --check-period 2024-01           # 指定月份
python -m app.scripts.manage --check-period 2024              # 指定年份
python -m app.scripts.manage --check-period 2024-01-15:2024-01-20  # 指定日期范围

# 自定义并发数
python -m app.scripts.manage --check-period today 10          # 今天，10并发
python -m app.scripts.manage --check-period week 5            # 最近7天，5并发
```

---

### 统计查看命令

```bash
# 查看检测统计
python -m app.scripts.manage --link-stats

# 查看失效链接详情
python -m app.scripts.manage --show-invalid-links             # 最近的失效链接
python -m app.scripts.manage --show-invalid-links "2024-01-15T14:30:00"  # 指定时间
python -m app.scripts.manage --show-invalid-links 50          # 最近50个

# 查看中断记录
python -m app.scripts.manage --show-interrupted
```

### 数据管理命令

```bash
# 清空所有检测数据 (需要确认)
python -m app.scripts.manage --clear-link-check-data

# 清空旧数据
python -m app.scripts.manage --clear-old-link-check-data      # 30天前 (默认)
python -m app.scripts.manage --clear-old-link-check-data 7    # 7天前
python -m app.scripts.manage --clear-old-link-check-data 60   # 60天前
```
