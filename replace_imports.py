import os
import re

# 替换规则（顺序很重要，先长后短）
replace_rules = [
    (r'^from\s+models\s+import', 'from app.models.models import'),
    (r'^from\s+db\s+import', 'from app.models.db import'),
    (r'^from\s+config\s+import', 'from app.models.config import'),
    (r'^from\s+link_validator\s+import', 'from app.core.link_validator import'),
    (r'^from\s+monitor\s+import', 'from app.core.monitor import'),
    (r'^from\s+admin\s+import', 'from app.web.admin import'),
    (r'^from\s+web\s+import', 'from app.web.web import'),
    (r'^from\s+add_user\s+import', 'from app.scripts.add_user import'),
    (r'^from\s+init_db\s+import', 'from app.scripts.init_db import'),
    (r'^from\s+manage\s+import', 'from app.scripts.manage import'),
]

# 递归遍历app目录下所有py文件
def get_py_files(root):
    py_files = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.endswith('.py'):
                py_files.append(os.path.join(dirpath, f))
    return py_files

py_files = get_py_files('app')

for file in py_files:
    with open(file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    changed = False
    new_lines = []
    for line in lines:
        orig_line = line
        for pattern, repl in replace_rules:
            if re.match(pattern, line):
                line = re.sub(pattern, repl, line)
                if line != orig_line:
                    print(f"[{file}] 替换: {orig_line.strip()} => {line.strip()}")
                    changed = True
        new_lines.append(line)
    if changed:
        with open(file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

print("批量import路径替换完成！请逐步测试入口脚本。") 