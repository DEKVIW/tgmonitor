from app.models.models import create_tables, Channel, engine, Base
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.config import settings
import json
import streamlit_authenticator as stauth
import os

def init_channels():
    # 从配置中获取默认频道列表
    default_channels = settings.DEFAULT_CHANNELS.split(',')
    
    # 创建数据库会话
    with Session(engine) as session:
        # 检查每个频道是否已存在
        for username in default_channels:
            username = username.strip()
            if not username:
                continue
                
            # 检查频道是否已存在
            existing = session.query(Channel).filter_by(username=username).first()
            if not existing:
                # 创建新频道记录
                channel = Channel(username=username)
                session.add(channel)
                print(f"添加频道: {username}")
        
        # 提交更改
        session.commit()

def init_default_users():
    """初始化默认用户"""
    USER_DATA_FILE = "users.json"
    
    # 默认用户配置
    default_users = {
        "admin": {
            "password": "admin123",  # 建议首次登录后修改
            "name": "系统管理员",
            "email": "admin@example.com",
            "role": "admin"
        }
    }
    
    # 检查用户文件是否存在
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                existing_users = json.load(f)
                print(f"发现现有用户文件，包含 {len(existing_users)} 个用户")
                return  # 如果文件已存在，不覆盖
        except Exception as e:
            print(f"读取现有用户文件失败: {e}")
    
    # 创建新用户文件
    try:
        # 生成 bcrypt 哈希密码 - 0.4.2版本的正确用法
        hasher = stauth.Hasher()
        users_with_hash = {}
        
        for username, user_info in default_users.items():
            hashed_password = hasher.hash(user_info["password"])
            users_with_hash[username] = {
                "password": hashed_password,
                "name": user_info["name"],
                "email": user_info["email"],
                "role": user_info.get("role", "user")
            }
        
        # 保存用户文件
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_with_hash, f, ensure_ascii=False, indent=2)
        
        print("✅ 默认用户创建成功！")
        print("📋 默认登录信息：")
        print("   用户名: admin")
        print("   密码: admin123")
        print("   角色: 系统管理员")
        print("⚠️  请首次登录后立即修改密码！")
        
    except Exception as e:
        print(f"❌ 创建默认用户失败: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("🗄️  TG监控系统 - 数据库初始化")
    print("=" * 50)
    
    # 创建所有表（使用JSONB类型）
    print("🏗️ 创建数据库表...")
    create_tables()
    
    # 验证表结构
    print("🔍 验证表结构...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'messages' 
            AND column_name = 'netdisk_types'
        """))
        for row in result:
            print(f"✅ {row[0]}: {row[1]}")
    
    print("正在初始化频道...")
    init_channels()
    print("正在初始化默认用户...")
    init_default_users()
    print("✅ 初始化完成！")
    print("\n📊 数据库特性：")
    print("   - netdisk_types 字段使用 JSONB 类型")
    print("   - 支持高性能的 JSON 查询")
    print("   - 支持 @> 包含操作符")
    print("   - 支持 jsonb_array_elements_text 函数") 