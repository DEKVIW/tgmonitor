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

# 检查是否提供了备份文件参数
if [ -z "$1" ]; then
    echo "请指定要恢复的备份文件"
    echo "使用方法: ./restore_db.sh 备份文件名"
    echo "例如: ./restore_db.sh tg_monitor_20240607_091557.sql.gz"
    echo ""
    echo "或者指定完整路径:"
    echo "例如: ./restore_db.sh /root/data/python/tg-monitor/backup/tg_monitor_20240607_091557.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# 如果提供的是相对路径，转换为绝对路径
if [[ "$BACKUP_FILE" != /* ]]; then
    # 检查是否在backup目录中
    if [[ "$BACKUP_FILE" == backup/* ]]; then
        BACKUP_FILE="$PROJECT_ROOT/$BACKUP_FILE"
    else
        BACKUP_FILE="$PROJECT_ROOT/backup/$BACKUP_FILE"
    fi
fi

# 检查备份文件是否存在
if [ ! -f "$BACKUP_FILE" ]; then
    echo "错误: 备份文件 $BACKUP_FILE 不存在"
    echo ""
    echo "可用的备份文件:"
    if [ -d "$PROJECT_ROOT/backup" ]; then
        ls -lh "$PROJECT_ROOT/backup"/tg_monitor_*.sql.gz 2>/dev/null | while read line; do
            echo "  $line"
        done
    else
        echo "  备份目录 $PROJECT_ROOT/backup 不存在"
    fi
    exit 1
fi

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
echo ""
echo "备份文件: $BACKUP_FILE"
echo "文件大小: $(du -h "$BACKUP_FILE" | cut -f1)"

# 确认操作
echo ""
echo "⚠️  警告: 此操作将覆盖现有数据库中的所有数据！"
read -p "确定要继续吗？(输入 'yes' 确认): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

# 设置数据库密码环境变量
export PGPASSWORD="$DB_PASS"

echo ""
echo "开始恢复数据库..."

# 如果是压缩文件，先解压再恢复
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "检测到压缩文件，正在解压并恢复..."
    if gunzip -c "$BACKUP_FILE" | psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME"; then
        echo "✅ 数据库恢复成功完成！"
    else
        echo "❌ 数据库恢复失败！"
        unset PGPASSWORD
        exit 1
    fi
else
    echo "检测到普通SQL文件，正在恢复..."
    if psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" < "$BACKUP_FILE"; then
        echo "✅ 数据库恢复成功完成！"
    else
        echo "❌ 数据库恢复失败！"
        unset PGPASSWORD
        exit 1
    fi
fi

# 清除密码环境变量
unset PGPASSWORD

echo ""
echo "🎉 数据库恢复任务完成！"
echo "现在可以启动服务了。" 