import json
import hashlib

def add_user(username, password, name, email):
    # 读取现有用户
    with open('users.json', 'r') as f:
        users = json.load(f)
    
    # 添加新用户
    users[username] = {
        "password": hashlib.sha256(password.encode()).hexdigest(),
        "name": name,
        "email": email
    }
    
    # 保存
    with open('users.json', 'w') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# 使用示例
add_user("newuser", "newpassword", "新用户", "newuser@example.com") 