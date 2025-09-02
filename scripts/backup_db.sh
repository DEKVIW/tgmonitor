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

# 从.env文件读取数据库配置
echo "正在读取数据库配置..."

# 读取DATABASE_URL并解析
DATABASE_URL=$(grep "^DATABASE_URL=" "$PROJECT_ROOT/.env" | cut -d'=' -f2-)

if [ -z "$DATABASE_URL" ]; then
    echo "错误: 在.env文件中未找到DATABASE_URL配置"
    exit 1
fi

# 解析DATABASE_URL: postgresql://username:password@host:port/database
# 提取各个组件
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*@[^:]*:\([^/]*\)/.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

# 验证解析结果
if [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_NAME" ]; then
    echo "错误: 无法解析DATABASE_URL: $DATABASE_URL"
    echo "请检查.env文件中的DATABASE_URL格式是否正确"
    echo "正确格式: postgresql://username:password@host:port/database"
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
    echo "✅ 备份成功完成: $BACKUP_FILE"
    
    # 获取备份文件大小
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "备份文件大小: $BACKUP_SIZE"
    
    # 只保留最新的3份备份
    echo "清理旧备份文件..."
    OLD_BACKUPS=$(ls -t "$BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | tail -n +4)
    if [ -n "$OLD_BACKUPS" ]; then
        echo "$OLD_BACKUPS" | xargs rm -f
        echo "已删除 $(echo "$OLD_BACKUPS" | wc -l) 个旧备份文件"
    else
        echo "没有需要清理的旧备份文件"
    fi
    
    # 显示当前备份文件列表
    echo ""
    echo "当前备份文件列表:"
    ls -lh "$BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | while read line; do
        echo "  $line"
    done
    
else
    echo "❌ 备份失败！"
    exit 1
fi

# 清除密码环境变量
unset PGPASSWORD

echo ""
echo "备份任务完成！" 