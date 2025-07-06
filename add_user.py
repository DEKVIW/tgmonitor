import json
import streamlit_authenticator as stauth

def add_user(username, password, name, email):
    # 读取现有用户
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
    except Exception:
        users = {}
    
    # 生成 bcrypt 哈希
    hasher = stauth.Hasher()
    hashed_password = hasher.hash(password)
    
    # 添加新用户
    users[username] = {
        "password": hashed_password,
        "name": name,
        "email": email
    }
    
    # 保存
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    print(f"用户 {username} 添加成功！")

# 使用示例
add_user("aabbcc", "password", "管理员", "admin@example.com")