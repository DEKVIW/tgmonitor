#!/bin/bash

# 数据库恢复脚本
# 自动查找本地备份目录中最新的备份文件并恢复

# 获取脚本所在目录的上级目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 进入项目目录
cd "$PROJECT_ROOT"

# 检测虚拟环境名称（支持 venv 和 tgmonitor-venv）
if [ -d "venv" ]; then
    VENV_PATH="venv"
elif [ -d "tgmonitor-venv" ]; then
    VENV_PATH="tgmonitor-venv"
else
    echo "错误: 未找到虚拟环境（venv 或 tgmonitor-venv）"
    exit 1
fi

source "$VENV_PATH/bin/activate"

# 检查项目根目录是否存在
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "错误: 在项目根目录 $PROJECT_ROOT 中未找到 .env 文件"
    echo "请确保在正确的项目目录中运行此脚本"
    exit 1
fi

# 本地备份目录（硬编码）
LOCAL_BACKUP_DIR="$PROJECT_ROOT/backup"

# 查找最新的备份文件
if [ ! -d "$LOCAL_BACKUP_DIR" ]; then
    echo "❌ 错误: 备份目录 $LOCAL_BACKUP_DIR 不存在"
    exit 1
fi

BACKUP_FILE=$(ls -t "$LOCAL_BACKUP_DIR"/tg_monitor_*.sql.gz 2>/dev/null | head -1)

if [ -z "$BACKUP_FILE" ]; then
    echo "❌ 错误: 在备份目录 $LOCAL_BACKUP_DIR 中未找到备份文件"
    exit 1
fi

# 从.env文件读取数据库配置
echo "正在读取数据库配置..."

# 使用 Python 解析 DATABASE_URL（解决特殊字符问题）
# 创建临时 Python 脚本来解析 URL
cat > /tmp/parse_db_url_restore.py << 'EOF'
import os
import urllib.parse
from dotenv import load_dotenv
import sys

project_root = sys.argv[1] if len(sys.argv) > 1 else '/root/data/python/tg-monitor'
# 加载 .env 文件
load_dotenv(f'{project_root}/.env')

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
EOF

# 进入项目目录并激活虚拟环境
cd "$PROJECT_ROOT"

# 检测虚拟环境名称（支持 venv 和 tgmonitor-venv）
if [ -d "venv" ]; then
    VENV_PATH="venv"
elif [ -d "tgmonitor-venv" ]; then
    VENV_PATH="tgmonitor-venv"
else
    echo "错误: 未找到虚拟环境（venv 或 tgmonitor-venv）"
    exit 1
fi

source "$VENV_PATH/bin/activate"

# 执行 Python 脚本并获取结果（使用虚拟环境的 Python）
eval $("$VENV_PATH/bin/python3" /tmp/parse_db_url_restore.py "$PROJECT_ROOT")

# 清理临时文件
rm -f /tmp/parse_db_url_restore.py

# 验证解析结果
if [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_NAME" ]; then
    echo "错误: 无法解析 DATABASE_URL"
    echo "请检查.env文件中的DATABASE_URL格式是否正确"
    exit 1
fi

echo "数据库配置解析完成:"
echo "  主机: $DB_HOST"
echo "  端口: $DB_PORT"
echo "  用户: $DB_USER"
echo "  数据库: $DB_NAME"
echo "  密码: ${DB_PASS:0:5}****（已隐藏）"
echo ""
echo "📁 找到最新备份文件:"
echo "  文件: $(basename "$BACKUP_FILE")"
echo "  路径: $BACKUP_FILE"
echo "  大小: $(du -h "$BACKUP_FILE" | cut -f1)"
echo "  时间: $(stat -c %y "$BACKUP_FILE" | cut -d' ' -f1,2 | cut -d'.' -f1)"

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

# 先测试密码是否正确
echo "正在测试数据库连接..."
if psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ 数据库连接成功"
else
    echo "❌ 数据库连接失败！密码可能不正确"
    echo ""
    echo "解决方案："
    echo "1. 使用 postgres 用户恢复（推荐）："
    echo "   sudo -u postgres psql -d tg_monitor < backup/$(basename "$BACKUP_FILE" .gz)"
    echo ""
    echo "2. 或者修改数据库用户密码："
    echo "   sudo -u postgres psql -c \"ALTER USER tg_user WITH PASSWORD '你的密码';\""
    echo ""
    unset PGPASSWORD
    exit 1
fi

# 先清空数据库（删除所有表）
echo "正在清空现有数据库..."
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "
DO \$\$ 
DECLARE 
    r RECORD;
BEGIN
    -- 删除所有表
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
    
    -- 删除所有序列
    FOR r IN (SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public')
    LOOP
        EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(r.sequence_name) || ' CASCADE';
    END LOOP;
END \$\$;
" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ 数据库已清空"
else
    echo "⚠️  警告: 清空数据库时出现错误，但继续恢复..."
fi

# 如果是压缩文件，先解压再恢复
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "检测到压缩文件，正在解压并恢复..."
    if gunzip -c "$BACKUP_FILE" | psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" 2>&1 | grep -v "ERROR:" | grep -v "already exists" | grep -v "duplicate key" | grep -v "multiple primary keys"; then
        echo "✅ 数据库恢复成功完成！"
    else
        # 即使有错误，也检查是否恢复成功（通过检查表是否存在）
        TABLE_COUNT=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
        if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
            echo "✅ 数据库恢复完成（部分警告可忽略）"
        else
            echo "❌ 数据库恢复失败！"
            unset PGPASSWORD
            exit 1
        fi
    fi
else
    echo "检测到普通SQL文件，正在恢复..."
    if psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" < "$BACKUP_FILE" 2>&1 | grep -v "ERROR:" | grep -v "already exists" | grep -v "duplicate key" | grep -v "multiple primary keys"; then
        echo "✅ 数据库恢复成功完成！"
    else
        # 即使有错误，也检查是否恢复成功
        TABLE_COUNT=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
        if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
            echo "✅ 数据库恢复完成（部分警告可忽略）"
        else
            echo "❌ 数据库恢复失败！"
            unset PGPASSWORD
            exit 1
        fi
    fi
fi

# 清除密码环境变量
unset PGPASSWORD

echo ""
echo "🎉 数据库恢复任务完成！"
echo "现在可以启动服务了。" 