#!/bin/bash

# 获取脚本所在目录的上级目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 进入项目目录并激活虚拟环境
cd "$PROJECT_ROOT"
source tgmonitor-venv/bin/activate

# 检查项目根目录是否存在
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "错误: 在项目根目录 $PROJECT_ROOT 中未找到 .env 文件"
    echo "请确保在正确的项目目录中运行此脚本"
    exit 1
fi

# 设置变量
# 备份到两个目录：云端和本地
CLOUD_BACKUP_DIR="/mnt/Google/backup/tg-monitor"  # 云端备份目录
LOCAL_BACKUP_DIR="$PROJECT_ROOT/backup"           # 本地备份目录
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILENAME="tg_monitor_$DATE.sql.gz"
CLOUD_BACKUP_FILE="$CLOUD_BACKUP_DIR/$BACKUP_FILENAME"
LOCAL_BACKUP_FILE="$LOCAL_BACKUP_DIR/$BACKUP_FILENAME"

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
echo "  云端备份目录: $CLOUD_BACKUP_DIR"
echo "  本地备份目录: $LOCAL_BACKUP_DIR"

# 创建备份目录
mkdir -p "$CLOUD_BACKUP_DIR"
mkdir -p "$LOCAL_BACKUP_DIR"

# 设置数据库密码环境变量
export PGPASSWORD="$DB_PASS"

echo "开始备份数据库..."

# 先备份到临时文件，然后复制到两个目录
TEMP_BACKUP_FILE="/tmp/$BACKUP_FILENAME"

# 执行备份到临时文件
if pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" | gzip > "$TEMP_BACKUP_FILE"; then
    # 获取备份文件大小
    BACKUP_SIZE=$(du -h "$TEMP_BACKUP_FILE" | cut -f1)
    
    # 复制到云端目录
    if cp "$TEMP_BACKUP_FILE" "$CLOUD_BACKUP_FILE"; then
        echo "✅ 云端备份成功: $CLOUD_BACKUP_FILE ($BACKUP_SIZE)"
        
        # 清理云端旧备份文件（保留最近3个）
        OLD_CLOUD_BACKUPS=$(ls -t "$CLOUD_BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | tail -n +4)
        if [ -n "$OLD_CLOUD_BACKUPS" ]; then
            echo "$OLD_CLOUD_BACKUPS" | xargs rm -f >/dev/null 2>&1
        fi
    else
        echo "⚠️  警告: 云端备份失败，但继续本地备份"
    fi
    
    # 复制到本地目录
    if cp "$TEMP_BACKUP_FILE" "$LOCAL_BACKUP_FILE"; then
        echo "✅ 本地备份成功: $LOCAL_BACKUP_FILE ($BACKUP_SIZE)"
        
        # 清理本地旧备份文件（保留最近3个）
        OLD_LOCAL_BACKUPS=$(ls -t "$LOCAL_BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | tail -n +4)
        if [ -n "$OLD_LOCAL_BACKUPS" ]; then
            echo "$OLD_LOCAL_BACKUPS" | xargs rm -f >/dev/null 2>&1
        fi
    else
        echo "⚠️  警告: 本地备份失败"
    fi
    
    # 删除临时文件
    rm -f "$TEMP_BACKUP_FILE"
    
    echo ""
    echo "🎉 备份任务完成！"
    
else
    # 失败时显示详细信息
    echo "❌ 备份失败！"
    echo "错误详情:"
    echo "  数据库: $DB_NAME"
    echo "  主机: $DB_HOST:$DB_PORT"
    echo "  用户: $DB_USER"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    rm -f "$TEMP_BACKUP_FILE"
    exit 1
fi

# 清除密码环境变量
unset PGPASSWORD 