#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Session 获取脚本
用于生成 Telegram 监控服务所需的 session 文件
"""

from telethon import TelegramClient
import os
import sys

def main():
    print("🔐 Telegram Session 获取工具")
    print("=" * 40)
    
    # 获取 API 凭据
    try:
        api_id = input("请输入 TELEGRAM_API_ID: ").strip()
        if not api_id:
            print("❌ API ID 不能为空")
            sys.exit(1)
        
        api_hash = input("请输入 TELEGRAM_API_HASH: ").strip()
        if not api_hash:
            print("❌ API Hash 不能为空")
            sys.exit(1)
        
        # 固定 session 文件名
        session_name = "tg_monitor_session"
        
        print(f"\n📱 正在创建 session 文件: {session_name}.session")
        print("请按照提示输入手机号和验证码...")
        
        # 创建客户端并启动登录流程
        client = TelegramClient(session_name, int(api_id), api_hash)
        
        # 启动客户端，这会触发登录流程
        client.start()
        
        print(f"\n✅ 登录成功！")
        print(f"📁 Session 文件已保存为: {session_name}.session")
        print(f"📍 文件位置: {os.path.abspath(session_name + '.session')}")
        print("\n💡 现在可以运行主监控程序了:")
        print("   python monitor.py")
        print("\n🚀 或者使用 Docker 部署:")
        print("   docker-compose up -d")
        
        # 断开连接
        client.disconnect()
        
    except KeyboardInterrupt:
        print("\n\n❌ 用户取消操作")
        sys.exit(1)
    except ValueError:
        print("❌ API ID 必须是数字")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 