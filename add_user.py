import json
import streamlit_authenticator as stauth

def add_user(username, password, name, email):
    # 读取现有用户
    with open('users.json', 'r') as f:
        users = json.load(f)
    
    # 生成 bcrypt 哈希（streamlit-authenticator 0.4.2 需要）
    hasher = stauth.Hasher()
    hashed_password = hasher.hash(password)
    
    # 添加新用户
    users[username] = {
        "password": hashed_password,
        "name": name,
        "email": email
    }
    
    # 保存
    with open('users.json', 'w') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# 使用示例
add_user("admin", "password", "管理员", "admin@example.com") 