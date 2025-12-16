import argparse
import json
from pathlib import Path

from passlib.context import CryptContext


USERS_FILE = Path("users.json")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def add_user(username: str, password: str, name: str, email: str, role: str = "admin") -> None:
    """向 users.json 添加一个用户，使用与后端一致的 bcrypt 哈希。"""
    # 读取现有用户
    if USERS_FILE.exists():
        try:
            with USERS_FILE.open("r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            users = {}
    else:
        users = {}

    # 生成 bcrypt 哈希（与后端登录校验一致）
    hashed_password = pwd_context.hash(password)

    # 添加/覆盖用户
    users[username] = {
        "password": hashed_password,
        "name": name,
        "email": email,
        "role": role,
    }

    # 保存
    with USERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

    print(f"用户 {username} 添加成功！")


def main() -> None:
    parser = argparse.ArgumentParser(description="向 users.json 添加后台登录用户")
    parser.add_argument("username", help="用户名（登录用）")
    parser.add_argument("password", help="明文密码")
    parser.add_argument("--name", default="系统管理员", help="显示名称")
    parser.add_argument("--email", default="admin@example.com", help="邮箱")
    parser.add_argument("--role", default="admin", help="角色，默认为 admin")

    args = parser.parse_args()
    add_user(args.username, args.password, args.name, args.email, args.role)


if __name__ == "__main__":
    main()