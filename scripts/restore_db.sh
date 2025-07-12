#!/bin/bash

# 检查是否提供了备份文件参数
if [ -z "$1" ]; then
    echo "请指定要恢复的备份文件"
    echo "使用方法: ./restore_db.sh 备份文件名"
    echo "例如: ./restore_db.sh tg_monitor_20240607_091557.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# 检查备份文件是否存在
if [ ! -f "$BACKUP_FILE" ]; then
    echo "错误: 备份文件 $BACKUP_FILE 不存在"
    exit 1
fi

# 设置数据库密码环境变量
export PGPASSWORD='1y&PpV%#usGpZS0!Yjx%'

echo "开始恢复数据库..."

# 如果是压缩文件，先解压再恢复
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | psql -U tg_user -h localhost -d tg_monitor
else
    psql -U tg_user -h localhost -d tg_monitor < "$BACKUP_FILE"
fi

# 清除密码环境变量
unset PGPASSWORD

echo "数据库恢复完成！" 