#!/bin/bash

# 设置变量
BACKUP_DIR="/root/data/python/tg-monitor/backup"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tg_monitor_$DATE.sql.gz"

# 设置数据库密码环境变量
export PGPASSWORD='password'

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
pg_dump -U tg_user -h localhost -d tg_monitor | gzip > $BACKUP_FILE

# 清除密码环境变量
unset PGPASSWORD

# 只保留最新的3份备份
ls -t $BACKUP_DIR/tg_monitor_*.sql.gz | tail -n +4 | xargs -r rm

# 输出备份信息
echo "备份完成: $BACKUP_FILE"
echo "当前备份文件列表:"
ls -lh $BACKUP_DIR/tg_monitor_*.sql.gz 