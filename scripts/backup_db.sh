#!/bin/bash

# 获取脚本所在目录的上级目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检查项目根目录是否存在
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "错误: 在项目根目录 $PROJECT_ROOT 中未找到 .env 文件"
    echo "请确保在正确的项目目录中运行此脚本"
    exit 1
fi

# 设置变量
BACKUP_DIR="/mnt/Google/backup/tg-monitor"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tg_monitor_$DATE.sql.gz"

# 使用 Python 解析 DATABASE_URL（解决特殊字符问题）
echo "正在读取数据库配置..."

# 创建临时 Python 脚本来解析 URL
cat > /tmp/parse_db_url.py << 'EOF'
import os
import urllib.parse
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv('/root/data/python/tg-monitor/.env')

# 获取 DATABASE_URL
database_url = os.getenv('DATABASE_URL')
if not database_url:
    print("错误: 未找到 DATABASE_URL")
    exit(1)

# 使用 urllib.parse.unquote 来正确解码 URL 编码的字符
parsed = urllib.parse.urlparse(database_url)

# 解码用户名和密码
username = urllib.parse.unquote(parsed.username) if parsed.username else ""
password = urllib.parse.unquote(parsed.password) if parsed.password else ""

# 输出解析结果
print(f"DB_USER={username}")
print(f"DB_PASS={password}")
print(f"DB_HOST={parsed.hostname}")
print(f"DB_PORT={parsed.port}")
print(f"DB_NAME={parsed.path[1:] if parsed.path else ''}")

# 调试信息
print(f"# 原始 DATABASE_URL: {database_url}")
print(f"# 解码后的密码: {password}")
EOF

# 执行 Python 脚本并获取结果
cd "$PROJECT_ROOT"
eval $(python3 /tmp/parse_db_url.py)

# 清理临时文件
rm -f /tmp/parse_db_url.py

# 验证解析结果
if [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_NAME" ]; then
    echo "错误: 无法解析 DATABASE_URL"
    exit 1
fi

echo "数据库配置解析完成:"
echo "  主机: $DB_HOST"
echo "  端口: $DB_PORT"
echo "  用户: $DB_USER"
echo "  数据库: $DB_NAME"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 设置数据库密码环境变量
export PGPASSWORD="$DB_PASS"

echo "开始备份数据库..."

# 执行备份
if pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    # 获取备份文件大小
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    
    # 成功时只显示一条简洁信息
    echo "✅ 备份成功: $BACKUP_FILE ($BACKUP_SIZE)"
    
    # 清理旧备份文件（静默执行）
    OLD_BACKUPS=$(ls -t "$BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | tail -n +4)
    if [ -n "$OLD_BACKUPS" ]; then
        echo "$OLD_BACKUPS" | xargs rm -f >/dev/null 2>&1
    fi
    
else
    # 失败时显示详细信息
    echo "❌ 备份失败！"
    echo "错误详情:"
    echo "  数据库: $DB_NAME"
    echo "  主机: $DB_HOST:$DB_PORT"
    echo "  用户: $DB_USER"
    echo "  目标文件: $BACKUP_FILE"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    exit 1
fi

# 清除密码环境变量
unset PGPASSWORD

echo ""
echo "备份任务完成！" 