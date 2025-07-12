#!/usr/bin/env python3
"""
生成 SECRET_SALT 密钥的脚本
用于用户登录验证
"""

import secrets
import string

def generate_secret_salt(length=64):
    """生成随机密钥"""
    # 使用字母、数字和特殊字符
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for _ in range(length))

def generate_hex_salt(length=32):
    """生成十六进制密钥"""
    return secrets.token_hex(length)

if __name__ == "__main__":
    print("🔐 SECRET_SALT 密钥生成器")
    print("=" * 50)
    
    # 生成多种格式的密钥
    print("1. 混合字符密钥（推荐）：")
    mixed_key = generate_secret_salt(64)
    print(f"   SECRET_SALT={mixed_key}")
    print()
    
    print("2. 十六进制密钥：")
    hex_key = generate_hex_salt(32)
    print(f"   SECRET_SALT={hex_key}")
    print()
    
    print("3. 短密钥（32字符）：")
    short_key = generate_secret_salt(32)
    print(f"   SECRET_SALT={short_key}")
    print()
    
    print("📝 使用方法：")
    print("1. 选择上面任意一个密钥")
    print("2. 复制到 .env 文件中")
    print("3. 确保密钥长度至少32字符")
    print()
    
    print("⚠️  安全提示：")
    print("- 请妥善保管密钥，不要泄露")
    print("- 不同环境应使用不同的密钥")
    print("- 定期更换密钥以提高安全性")
    print("- 密钥一旦设置，不要随意更改（会影响现有用户登录）") 