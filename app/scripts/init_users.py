#!/usr/bin/env python3
"""
用户初始化脚本
用于创建和管理系统用户
"""

import json
import os
import sys
from typing import Dict, Any

from passlib.context import CryptContext

USER_DATA_FILE = "users.json"

# 用户角色定义
USER_ROLES = {
    "admin": "系统管理员",
    "user": "普通用户",
    "viewer": "只读用户"
}

# 与后端 app.services.auth_service 使用的配置保持一致
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_existing_users() -> Dict[str, Any]:
    """加载现有用户"""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取用户文件失败: {e}")
            return {}
    return {}

def save_users(users: Dict[str, Any]):
    """保存用户数据"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        print("✅ 用户数据保存成功！")
    except Exception as e:
        print(f"❌ 保存用户数据失败: {e}")

def create_default_users():
    """创建默认用户"""
    users = load_existing_users()
    
    # 默认用户配置
    default_users = {
        "admin": {
            "password": "admin123",
            "name": "系统管理员",
            "email": "admin@example.com",
            "role": "admin"
        }
    }
    
    # 检查是否已有用户
    if users:
        print(f"发现现有用户文件，包含 {len(users)} 个用户")
        print("现有用户:", list(users.keys()))
        return
    
    # 创建默认用户（使用 passlib bcrypt，与后端保持一致）
    for username, user_info in default_users.items():
        hashed_password = pwd_context.hash(user_info["password"])
        users[username] = {
            "password": hashed_password,
            "name": user_info["name"],
            "email": user_info["email"],
            "role": user_info.get("role", "user")
        }
    
    save_users(users)
    
    print("✅ 默认用户创建成功！")
    print("📋 默认登录信息：")
    print("   用户名: admin")
    print("   密码: admin123")
    print("   角色: 系统管理员")
    print("⚠️  请首次登录后立即修改密码！")

def add_user(username: str, password: str, name: str = "", email: str = "", role: str = "user"):
    """添加新用户"""
    users = load_existing_users()
    
    if username in users:
        print(f"❌ 用户 {username} 已存在！")
        return False
    
    # 验证角色
    if role not in USER_ROLES:
        print(f"❌ 无效的角色: {role}")
        print(f"可用角色: {', '.join(USER_ROLES.keys())}")
        return False
    
    # 生成密码哈希（与后端一致）
    hashed_password = pwd_context.hash(password)
    
    # 添加用户
    users[username] = {
        "password": hashed_password,
        "name": name or username,
        "email": email,
        "role": role
    }
    
    save_users(users)
    print(f"✅ 用户 {username} 添加成功！")
    print(f"   角色: {USER_ROLES[role]}")
    return True

def remove_user(username: str):
    """删除用户"""
    users = load_existing_users()
    
    if username not in users:
        print(f"❌ 用户 {username} 不存在！")
        return False
    
    if username == "admin":
        print("❌ 不能删除管理员用户！")
        return False
    
    del users[username]
    save_users(users)
    print(f"✅ 用户 {username} 删除成功！")
    return True

def list_users():
    """列出所有用户"""
    users = load_existing_users()
    
    if not users:
        print("📝 暂无用户")
        return
    
    print(f"📝 共 {len(users)} 个用户：")
    print("-" * 60)
    for username, user_info in users.items():
        role_name = USER_ROLES.get(user_info.get('role', 'user'), '未知角色')
        print(f"用户名: {username}")
        print(f"姓名: {user_info.get('name', 'N/A')}")
        print(f"邮箱: {user_info.get('email', 'N/A')}")
        print(f"角色: {role_name}")
        print("-" * 60)

def change_password(username: str, new_password: str):
    """修改用户密码"""
    users = load_existing_users()
    
    if username not in users:
        print(f"❌ 用户 {username} 不存在！")
        return False
    
    # 生成新密码哈希（与后端一致）
    hashed_password = pwd_context.hash(new_password)
    
    # 更新密码
    users[username]["password"] = hashed_password
    save_users(users)
    print(f"✅ 用户 {username} 密码修改成功！")
    return True

def change_username(old_username: str, new_username: str):
    """修改用户名"""
    users = load_existing_users()
    
    if old_username not in users:
        print(f"❌ 用户 {old_username} 不存在！")
        return False
    
    if new_username in users:
        print(f"❌ 用户名 {new_username} 已存在！")
        return False
    
    # 移动用户数据
    users[new_username] = users.pop(old_username)
    save_users(users)
    print(f"✅ 用户名从 {old_username} 修改为 {new_username} 成功！")
    return True

def change_user_role(username: str, new_role: str):
    """修改用户角色"""
    users = load_existing_users()
    
    if username not in users:
        print(f"❌ 用户 {username} 不存在！")
        return False
    
    if new_role not in USER_ROLES:
        print(f"❌ 无效的角色: {new_role}")
        print(f"可用角色: {', '.join(USER_ROLES.keys())}")
        return False
    
    # 更新角色
    users[username]["role"] = new_role
    save_users(users)
    print(f"✅ 用户 {username} 角色修改为 {USER_ROLES[new_role]} 成功！")
    return True

def edit_user_info(username: str, name: str = None, email: str = None):
    """编辑用户信息"""
    users = load_existing_users()
    
    if username not in users:
        print(f"❌ 用户 {username} 不存在！")
        return False
    
    # 更新信息
    if name is not None:
        users[username]["name"] = name
    if email is not None:
        users[username]["email"] = email
    
    save_users(users)
    print(f"✅ 用户 {username} 信息修改成功！")
    return True

def list_roles():
    """列出所有可用角色"""
    print("📋 可用角色：")
    for role, description in USER_ROLES.items():
        print(f"  {role}: {description}")

def print_help():
    """打印帮助信息"""
    print("""
用户管理脚本使用方法：

1. 创建默认用户：
   python -m app.scripts.init_users --create-default

2. 添加新用户：
   python -m app.scripts.init_users --add-user 用户名 密码 [姓名] [邮箱] [角色]

3. 删除用户：
   python -m app.scripts.init_users --remove-user 用户名

4. 修改密码：
   python -m app.scripts.init_users --change-password 用户名 新密码

5. 修改用户名：
   python -m app.scripts.init_users --change-username 旧用户名 新用户名

6. 修改用户角色：
   python -m app.scripts.init_users --change-role 用户名 新角色

7. 编辑用户信息：
   python -m app.scripts.init_users --edit-user 用户名 [姓名] [邮箱]

8. 列出所有用户：
   python -m app.scripts.init_users --list-users

9. 列出所有角色：
   python -m app.scripts.init_users --list-roles

10. 显示帮助：
    python -m app.scripts.init_users --help

可用角色：
  admin: 系统管理员
  user: 普通用户
  viewer: 只读用户

示例：
   python -m app.scripts.init_users --create-default
   python -m app.scripts.init_users --add-user user1 password123 "用户1" "user1@example.com" user
   python -m app.scripts.init_users --change-password admin newpassword123
   python -m app.scripts.init_users --change-username user1 user2
   python -m app.scripts.init_users --change-role user1 admin
   python -m app.scripts.init_users --edit-user user1 "新姓名" "newemail@example.com"
   python -m app.scripts.init_users --list-users
   python -m app.scripts.init_users --list-roles
""")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_help()
        return
    
    command = sys.argv[1]
    
    if command == "--create-default":
        create_default_users()
    
    elif command == "--add-user":
        if len(sys.argv) < 4:
            print("❌ 请提供用户名和密码")
            return
        username = sys.argv[2]
        password = sys.argv[3]
        name = sys.argv[4] if len(sys.argv) > 4 else ""
        email = sys.argv[5] if len(sys.argv) > 5 else ""
        role = sys.argv[6] if len(sys.argv) > 6 else "user"
        add_user(username, password, name, email, role)
    
    elif command == "--remove-user":
        if len(sys.argv) < 3:
            print("❌ 请提供用户名")
            return
        username = sys.argv[2]
        remove_user(username)
    
    elif command == "--change-password":
        if len(sys.argv) < 4:
            print("❌ 请提供用户名和新密码")
            return
        username = sys.argv[2]
        new_password = sys.argv[3]
        change_password(username, new_password)
    
    elif command == "--change-username":
        if len(sys.argv) < 4:
            print("❌ 请提供旧用户名和新用户名")
            return
        old_username = sys.argv[2]
        new_username = sys.argv[3]
        change_username(old_username, new_username)
    
    elif command == "--change-role":
        if len(sys.argv) < 4:
            print("❌ 请提供用户名和新角色")
            return
        username = sys.argv[2]
        new_role = sys.argv[3]
        change_user_role(username, new_role)
    
    elif command == "--edit-user":
        if len(sys.argv) < 3:
            print("❌ 请提供用户名")
            return
        username = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else None
        email = sys.argv[4] if len(sys.argv) > 4 else None
        edit_user_info(username, name, email)
    
    elif command == "--list-users":
        list_users()
    
    elif command == "--list-roles":
        list_roles()
    
    elif command == "--help":
        print_help()
    
    else:
        print(f"❌ 未知命令: {command}")
        print_help()

if __name__ == "__main__":
    main() 