#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建链接检测相关的数据库表
安全版本 - 包含数据备份建议和详细检查
"""

from models import create_tables, LinkCheckStats, LinkCheckDetails
from sqlalchemy.orm import Session
from models import engine
from sqlalchemy import inspect

def check_table_exists(table_name):
    """检查表是否已存在"""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    return table_name in existing_tables

def create_link_check_tables():
    """创建链接检测相关的表"""
    print("🔒 安全检查：链接检测表创建")
    print("=" * 50)
    
    # 1. 检查现有表
    print("📋 检查现有表结构...")
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    print(f"现有表: {', '.join(existing_tables)}")
    
    # 2. 检查新表是否已存在
    new_tables = ['link_check_stats', 'link_check_details']
    existing_new_tables = [table for table in new_tables if check_table_exists(table)]
    
    if existing_new_tables:
        print(f"⚠️  发现已存在的表: {', '.join(existing_new_tables)}")
        print("这些表将被跳过，不会重新创建")
    
    # 3. 安全建议
    print("\n🔒 安全建议:")
    print("- 此操作只创建新表，不会修改现有数据")
    print("- 建议在操作前备份数据库（可选）")
    print("- 如果表已存在，将跳过创建")
    
    # 4. 确认操作
    response = input("\n是否继续创建表？(y/N): ").strip().lower()
    if response != 'y':
        print("❌ 操作已取消")
        return False
    
    try:
        print("\n🚀 开始创建表...")
        
        # 创建所有表（只创建不存在的）
        create_tables()
        print("✅ 数据库表创建成功！")
        
        # 验证表是否创建成功
        print("🔍 验证表结构...")
        with Session(engine) as session:
            # 测试插入一条记录
            test_stats = LinkCheckStats(
                check_time=datetime.now(),
                total_messages=0,
                total_links=0,
                valid_links=0,
                invalid_links=0,
                netdisk_stats={},
                check_duration=0.0,
                status='test'
            )
            session.add(test_stats)
            session.commit()
            
            # 删除测试记录
            session.delete(test_stats)
            session.commit()
            
        print("✅ 表结构验证成功！")
        
        # 最终检查
        final_tables = inspector.get_table_names()
        created_tables = [table for table in new_tables if table in final_tables]
        
        print(f"\n📊 创建结果:")
        print(f"- 成功创建的表: {', '.join(created_tables)}")
        print(f"- 总表数量: {len(final_tables)}")
        
        print("\n🎉 迁移完成！现有数据完全安全。")
        
    except Exception as e:
        print(f"❌ 创建表失败: {str(e)}")
        print("💡 建议检查数据库权限和连接")
        return False
    
    return True

if __name__ == "__main__":
    from datetime import datetime
    create_link_check_tables() 