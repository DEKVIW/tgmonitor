import os
import shutil

# 目标目录结构
dirs = [
    "app/core",
    "app/web",
    "app/models",
    "app/scripts",
    "app/utils"
]

# 创建目录和 __init__.py
for d in dirs:
    os.makedirs(d, exist_ok=True)
    init_file = os.path.join(d, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "w").close()

# 文件移动映射
move_map = {
    "monitor.py": "app/core/monitor.py",
    "link_validator.py": "app/core/link_validator.py",
    "web.py": "app/web/web.py",
    "admin.py": "app/web/admin.py",
    "models.py": "app/models/models.py",
    "db.py": "app/models/db.py",
    "config.py": "app/models/config.py",
    "init_db.py": "app/scripts/init_db.py",
    "add_user.py": "app/scripts/add_user.py",
    "manage.py": "app/scripts/manage.py"
}

for src, dst in move_map.items():
    if os.path.exists(src):
        print(f"移动 {src} -> {dst}")
        shutil.move(src, dst)
    else:
        print(f"未找到 {src}，跳过。")

print("目录和文件移动完成！") 