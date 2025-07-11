# TG Monitor

基于 Python + Telethon + Streamlit 的 Telegram 频道消息监控与管理系统。

- 自动监听指定 Telegram 频道消息，只保存包含网盘链接的消息
- Web 界面可视化浏览和筛选消息
- 支持频道管理、消息去重、标签修复等维护功能
- 支持 systemd/定时任务后台运行，日志可查

## 环境与依赖版本建议

- **推荐 Python 版本**：3.10 或 3.11（3.12 也可，优先用 3.10/3.11，兼容性最佳）
  - Python 3.8 也能运行，但不推荐，未来部分依赖可能不再支持。
  - Python 3.9 及以上均可，建议开发和生产环境保持一致。
- **推荐 PostgreSQL 版本**：13、14 或 15
  - 兼容 12~16，推荐用 13/14/15，社区支持好，性能优良。
- **依赖安装**：已在 requirements.txt 中声明，`pip install -r requirements.txt` 一键安装。
- **注意**：如用 Docker，建议基础镜像用 `python:3.10-slim` 和 `postgres:15`。

---

## 🐳 Docker 部署说明

### 1. 目录结构建议

```
tg-monitor/
├── app/
├── data/
├── users.json
├── requirements.txt
├── .env
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── ...
```

### 2. 环境准备

- 推荐 Python 3.10/3.11，PostgreSQL 13/14/15（镜像已内置，无需手动安装）
- `.env`、`users.json`、`data/` 目录建议提前准备好

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
```

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

### 6. 首次 Telethon 登录

**方法一：推荐 - 本地生成 session 文件**

1. 本地运行监控服务进行登录：
   ```bash
   docker-compose run --rm monitor python -m app.core.monitor
   ```
2. 按提示输入手机号、验证码
   - **手机号格式**：`+国家代码手机号`（如：`+8613812345678`）
3. 登录成功后，session 文件会自动保存到 `data/` 目录

**方法二：使用已有 session 文件**

如果你已有 session 文件，直接放到 `data/` 目录：

```bash
cp your_session.session data/tg_monitor_session.session
```

**Session 文件说明**：

- 文件名：`tg_monitor_session.session`
- 包含 Telegram 登录凭据，无需重复登录
- 请妥善保管，不要泄露给他人
- 如果 session 失效，删除文件重新登录即可

### 7. 管理脚本用法

```bash
docker-compose run --rm monitor python -m app.scripts.manage --list-channels
docker-compose run --rm monitor python -m app.scripts.manage --add-channel 频道名
docker-compose run --rm monitor python -m app.scripts.manage --dedup-links
```

**用户管理命令**：

```bash
docker-compose run --rm monitor python -m app.scripts.init_users --create-default
docker-compose run --rm monitor python -m app.scripts.init_users --add-user 用户名 密码
docker-compose run --rm monitor python -m app.scripts.init_users --change-password 用户名 新密码
docker-compose run --rm monitor python -m app.scripts.init_users --change-username 旧用户名 新用户名
docker-compose run --rm monitor python -m app.scripts.init_users --edit-user 用户名 [姓名] [邮箱]
docker-compose run --rm monitor python -m app.scripts.init_users --list-users
```

### 8. 数据持久化与备份

- `data/` 目录、`users.json`、数据库数据卷都已挂载，重启容器不会丢失数据
- 数据库备份/恢复可用 `backup_db.sh`、`restore_db.sh`，或用 `docker exec` 进入 db 容器操作

### 9. 其它注意事项

- `.env` 文件中的 `DATABASE_URL` 主机名应为 `db`，如：
  ```
  DATABASE_URL=postgresql://tg_user:password@db:5432/tg_monitor
  ```
- **SECRET_SALT 密钥**：用于用户登录验证，建议使用随机生成的强密钥
  - 可以使用在线工具生成：https://www.random.org/strings/
  - 或使用命令生成：`openssl rand -hex 32`
  - 示例：`SECRET_SALT=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234`
- 日志文件建议输出到 `data/` 目录，便于查看和备份
- 管理脚本、初始化等操作都建议用 `docker-compose run --rm ...` 方式临时运行

## 快速部署

### 1. 克隆项目

```bash
git clone <你的仓库地址>
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

**⚠️ 重要提示：**

1. **SECRET_SALT 密钥**：用于用户登录验证，建议使用随机生成的强密钥

   - 可以使用项目提供的脚本生成：`python generate_secret.py`
   - 可以使用在线工具生成：https://www.random.org/strings/
   - 或使用命令生成：`openssl rand -hex 32`
   - 示例：`SECRET_SALT=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234`

2. **数据库密码包含特殊字符时的转义处理**

如果数据库密码包含特殊字符（如 `#`、`@`、`%`、`&`、`+`、`=`、`!`、`$`、`*`、`(`、`)`、`[`、`]`、`{`、`}`、`|`、`\`、`:`、`;`、`"`、`'`、`<`、`>`、`,`、`/`、`?`），需要进行 URL 编码转义。

**示例**：

- 原始密码：`1j7wxLn#ZTlNZ#3tpkwF`
- 转义后：`1j7wxLn%23ZTlNZ%233tpkwF`（`#` 转义为 `%23`）

**在线 URL 编码工具**：[Online URL Encoder](https://www.url-encode-decode.com/)

**完整示例**：

```
# 原始密码：1j7wxLn#ZTlNZ#3tpkwF
DATABASE_URL=postgresql://tg_user:1j7wxLn%23ZTlNZ%233tpkwF@localhost:5432/tg_monitor
SECRET_SALT=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234
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

### 7. 首次 Telethon 登录

**方法一：推荐 - 本地生成 session 文件**

1. 本地运行监控服务进行登录：
   ```bash
   python -m app.core.monitor
   ```
2. 按提示输入手机号、验证码
   - **手机号格式**：`+国家代码手机号`（如：`+8613812345678`）
3. 登录成功后，session 文件会自动保存为 `tg_monitor_session.session`
4. 将 session 文件放到正确位置：
   - **普通部署**：放到项目根目录
   - **Docker 部署**：放到 `data/` 目录

**方法二：使用已有 session 文件**

如果你已有 session 文件，直接放到 `data/` 目录：

- **普通部署**：`/path/to/tgmonitor/tg_monitor_session.session`
- **Docker 部署**：`data/tg_monitor_session.session`

**Session 文件说明**：

- 文件名：`tg_monitor_session.session`
- 包含 Telegram 登录凭据，无需重复登录
- 请妥善保管，不要泄露给他人
- 如果 session 失效，删除文件重新登录即可

### 8. 启动服务

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

## 其他说明

- 支持 systemd 服务和定时任务，详见文档或源码注释。
- 日志、会话等文件统一放在 `data/` 目录，便于管理。
- 代码结构清晰，易于二次开发和维护。

如需详细文档或遇到问题，欢迎提 issue 或 PR！

# 🔗 链接检测功能使用说明

## 📋 功能概述

链接检测系统可以检测数据库中各种网盘链接的有效性，支持多种检测方式、时间段选择、中断恢复、详细统计报告和数据管理功能。

### 🛡️ 安全特性

- **网盘特定限制**: 不同网盘使用不同的并发数和延迟策略
- **错误计数保护**: 自动暂停错误过多的网盘检测
- **随机延迟**: 避免被识别为机器人
- **用户确认**: 大规模检测前需要用户确认
- **安全中断**: 支持 Ctrl+C 安全中断并保存结果

---

## 🚀 快速开始

### 5 分钟快速上手

```bash
# 1. 首次使用 - 小规模测试
python -m app.scripts.manage --check-links 1 3

# 2. 扩大范围 - 检测最近24小时
python -m app.scripts.manage --check-links 24 5

# 3. 查看结果
python -m app.scripts.manage --link-stats
python -m app.scripts.manage --show-invalid-links
```

---

## 📊 核心检测命令

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

## 📈 统计查看命令

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

---

## 🗑️ 数据管理命令

```bash
# 清空所有检测数据 (需要确认)
python -m app.scripts.manage --clear-link-check-data

# 清空旧数据
python -m app.scripts.manage --clear-old-link-check-data      # 30天前 (默认)
python -m app.scripts.manage --clear-old-link-check-data 7    # 7天前
python -m app.scripts.manage --clear-old-link-check-data 60   # 60天前
```

---

## 📊 网盘支持与限制

| 网盘类型 | 最大并发 | 延迟范围 | 域名           |
| -------- | -------- | -------- | -------------- |
| 百度网盘 | 3        | 1-3 秒   | pan.baidu.com  |
| 夸克网盘 | 5        | 0.5-2 秒 | pan.quark.cn   |
| 阿里云盘 | 4        | 1-2.5 秒 | www.alipan.com |
| 115 网盘 | 2        | 2-4 秒   | 115.com        |
| 天翼云盘 | 3        | 1-3 秒   | cloud.189.cn   |
| 123 云盘 | 3        | 1-2 秒   | www.123pan.com |
| UC 网盘  | 3        | 1-2 秒   | drive.uc.cn    |
| 迅雷网盘 | 3        | 1-2 秒   | pan.xunlei.com |

### 安全限制

- **单次检测最大链接数**: 1000 个
- **全局最大并发数**: 10 个
- **全量检测最大并发**: 3 个
- **每个网盘最大错误数**: 10 个

---

## 🎯 使用场景与策略

### 日常监控

```bash
python -m app.scripts.manage --check-period today 10          # 每天检测今天的数据
# 预计时间：5-15分钟
```

### 周报分析

```bash
python -m app.scripts.manage --check-period week 10           # 检测本周数据
# 预计时间：30分钟-1小时
```

### 月度统计

```bash
python -m app.scripts.manage --check-period month 10          # 检测本月数据
# 预计时间：1-2小时
```

### 大规模检测

```bash
python -m app.scripts.manage --check-all-links 10             # 检测所有历史链接
# 预计时间：1-3小时 (取决于链接数量)
```

### 分批检测策略

```bash
# 第1步：检测最近7天
python -m app.scripts.manage --check-period week 10

# 第2步：检测最近30天
python -m app.scripts.manage --check-period month 10

# 第3步：检测历史数据
python -m app.scripts.manage --check-all-links 10
```

---

## ⚠️ 安全警告

检测前会显示的安全警告：

```
🚨 链接检测安全警告
============================================================
📊 检测规模:
   - 链接数量: 500
   - 最大并发: 5
   - 预计耗时: 3.3 - 6.7 分钟

⚠️  风险提示:
   - 高频率请求可能触发网盘反爬虫机制
   - 可能导致IP被临时限制访问
   - 建议在非高峰期进行大规模检测

🛡️  安全措施:
   - 已启用网盘特定的请求限制
   - 随机延迟避免被识别为机器人
   - 错误计数保护机制
   - 支持 Ctrl+C 安全中断

💡 建议:
   - 首次检测建议使用较小的并发数 (3-5)
   - 观察检测结果后再调整参数
   - 如遇到大量错误，请降低并发数或暂停检测
```

---

## 🔧 故障排除

### 常见问题

**Q: 检测速度很慢**
A: 这是正常的，延迟机制确保安全，不要随意提高并发数

**Q: 某个网盘一直失败**
A: 该网盘可能已达到错误限制，等待一段时间后重试

**Q: 检测过程中出现大量错误**
A: 降低并发数，检查网络连接，确认网盘服务正常

**Q: 检测被中断**
A: 使用 `--show-interrupted` 查看记录，重新运行

### 错误处理

- **网络超时**: 自动重试，增加错误计数
- **HTTP 错误**: 记录状态码，增加错误计数
- **网盘限制**: 自动暂停该网盘检测
- **用户中断**: 安全保存已完成结果

---

## 📋 性能参考

### 基于不同并发数的检测时间

| 链接数量 | 5 并发     | 10 并发    | 15 并发    | 20 并发    |
| -------- | ---------- | ---------- | ---------- | ---------- |
| 1,000    | 8-12 分钟  | 4-6 分钟   | 3-4 分钟   | 2-3 分钟   |
| 5,000    | 40-60 分钟 | 20-30 分钟 | 15-20 分钟 | 10-15 分钟 |
| 10,000   | 1.3-2 小时 | 40-60 分钟 | 30-40 分钟 | 20-30 分钟 |

### 并发数设置建议

- **小规模检测** (1000 链接以下)：5-10 并发
- **中等规模检测** (1000-5000 链接)：10-15 并发
- **大规模检测** (5000 链接以上)：15-20 并发

---

## 🗂️ 数据管理策略

### 定期清理策略

```bash
# 每周清理7天前的数据
python -m app.scripts.manage --clear-old-link-check-data 7

# 每月清理30天前的数据
python -m app.scripts.manage --clear-old-link-check-data 30

# 每季度清理90天前的数据
python -m app.scripts.manage --clear-old-link-check-data 90
```

### 数据保留建议

- **最近 7 天** - 保留用于日常监控
- **最近 30 天** - 保留用于月度分析
- **超过 90 天** - 可以安全删除

---

## 🎯 最佳实践

### 安全使用

- ✅ **首次使用从小规模开始**
- ✅ **观察错误率，及时调整并发数**
- ✅ **在非高峰期进行大规模检测**
- ❌ **不要随意提高并发数**
- ❌ **不要在网盘服务高峰期检测**

### 中断处理

- 按 `Ctrl+C` 可以安全中断
- 中断时会自动保存已完成结果
- 可以重新运行命令完成剩余检测

### 数据管理

- **不可恢复** - 清空操作不可撤销
- **谨慎使用** - 建议先备份重要数据
- **定期清理** - 避免数据库过大
- **保留分析** - 建议保留最近 30 天数据

---

## 📞 技术支持

如遇到问题，请检查：

1. 网络连接是否正常
2. 数据库连接是否正常
3. 网盘服务是否可用
4. 安全配置是否合理

**查看帮助**: `python -m app.scripts.manage --help`

---

**注意**: 链接检测功能会向网盘服务器发送请求，请合理使用，避免对网盘服务造成过大压力。
