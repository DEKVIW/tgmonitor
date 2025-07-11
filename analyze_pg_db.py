import os
import sys
from sqlalchemy import create_engine, text

# 读取环境变量或直接写死你的DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://tg_user:jeA%40b7E%40oo%25SDxsUDKhL@localhost:5432/tg_monitor"

def analyze():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("【messages表结构】")
        result = conn.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'messages'
            ORDER BY ordinal_position
        """))
        for row in result:
            print(f"{row[0]:20} {row[1]:10} {row[2]}")
        print("\n【netdisk_types字段样本】")
        result = conn.execute(text("""
            SELECT netdisk_types FROM messages
            WHERE netdisk_types IS NOT NULL
            LIMIT 3
        """))
        for i, row in enumerate(result, 1):
            print(f"样本{i}: {row[0]}")
        print("\n【netdisk_types字段类型测试】")
        try:
            conn.execute(text("SELECT jsonb_array_elements_text(netdisk_types) FROM messages WHERE netdisk_types IS NOT NULL LIMIT 1"))
            print("✅ 支持jsonb_array_elements_text(netdisk_types)")
        except Exception as e:
            print("❌ 不支持jsonb_array_elements_text(netdisk_types):", e)
        try:
            conn.execute(text("SELECT json_array_elements_text(netdisk_types::json) FROM messages WHERE netdisk_types IS NOT NULL LIMIT 1"))
            print("✅ 支持json_array_elements_text(netdisk_types::json)")
        except Exception as e:
            print("❌ 不支持json_array_elements_text(netdisk_types::json):", e)
        print("\n【@>操作符测试】")
        try:
            conn.execute(text("SELECT 1 FROM messages WHERE netdisk_types @> '[\"百度网盘\"]' LIMIT 1"))
            print("✅ 支持 netdisk_types @> '[\"百度网盘\"]'")
        except Exception as e:
            print("❌ 不支持 netdisk_types @> '[\"百度网盘\"]':", e)
        try:
            conn.execute(text("SELECT 1 FROM messages WHERE netdisk_types::jsonb @> '[\"百度网盘\"]'::jsonb LIMIT 1"))
            print("✅ 支持 netdisk_types::jsonb @> '[\"百度网盘\"]'::jsonb")
        except Exception as e:
            print("❌ 不支持 netdisk_types::jsonb @> '[\"百度网盘\"]'::jsonb:", e)

if __name__ == "__main__":
    analyze()