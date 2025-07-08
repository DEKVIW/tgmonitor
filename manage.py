import sys
from sqlalchemy.orm import Session
from models import Channel, Message, engine, DedupStats, LinkCheckStats, LinkCheckDetails
from sqlalchemy import update, delete
import ast
from datetime import datetime, timedelta
import json
from collections import defaultdict
from sqlalchemy import text
import asyncio
import time
import signal
import os

# 新增：导入链接检测模块
try:
    from link_validator import LinkValidator
    LINK_VALIDATOR_AVAILABLE = True
except ImportError:
    LINK_VALIDATOR_AVAILABLE = False
    print("⚠️  警告: link_validator.py 未找到，链接检测功能不可用")

# 全局变量用于中断处理
current_check_session = None
interrupted = False

# 新增：安全检测配置
SAFETY_CONFIG = {
    'max_links_per_check': 1000,  # 单次检测最大链接数
    'max_concurrent_global': 10,  # 全局最大并发数
    'require_confirmation': True,  # 是否需要用户确认
    'show_safety_warnings': True,  # 是否显示安全警告
}

def show_safety_warnings(url_count, max_concurrent):
    """显示安全警告信息"""
    print("\n" + "="*60)
    print("🚨 链接检测安全警告")
    print("="*60)
    print(f"📊 检测规模:")
    print(f"   - 链接数量: {url_count}")
    print(f"   - 最大并发: {max_concurrent}")
    print(f"   - 预计耗时: {url_count * 2 / max_concurrent:.1f} - {url_count * 4 / max_concurrent:.1f} 分钟")
    
    print(f"\n⚠️  风险提示:")
    print(f"   - 高频率请求可能触发网盘反爬虫机制")
    print(f"   - 可能导致IP被临时限制访问")
    print(f"   - 建议在非高峰期进行大规模检测")
    
    print(f"\n🛡️  安全措施:")
    print(f"   - 已启用网盘特定的请求限制")
    print(f"   - 随机延迟避免被识别为机器人")
    print(f"   - 错误计数保护机制")
    print(f"   - 支持 Ctrl+C 安全中断")
    
    print(f"\n💡 建议:")
    print(f"   - 首次检测建议使用较小的并发数 (3-5)")
    print(f"   - 观察检测结果后再调整参数")
    print(f"   - 如遇到大量错误，请降低并发数或暂停检测")
    print("="*60)

def confirm_large_check(url_count, max_concurrent):
    """确认大规模检测"""
    if not SAFETY_CONFIG['require_confirmation']:
        return True
    
    if url_count > 100 or max_concurrent > 5:
        show_safety_warnings(url_count, max_concurrent)
        
        while True:
            response = input(f"\n❓ 确认开始检测 {url_count} 个链接 (并发 {max_concurrent})? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', '']:
                print("❌ 检测已取消")
                return False
            else:
                print("请输入 y 或 n")
    
    return True

def check_safety_limits(url_count, max_concurrent):
    """检查安全限制"""
    if url_count > SAFETY_CONFIG['max_links_per_check']:
        print(f"❌ 链接数量 ({url_count}) 超过安全限制 ({SAFETY_CONFIG['max_links_per_check']})")
        print(f"💡 建议分批检测或调整 SAFETY_CONFIG['max_links_per_check']")
        return False
    
    if max_concurrent > SAFETY_CONFIG['max_concurrent_global']:
        print(f"❌ 并发数 ({max_concurrent}) 超过安全限制 ({SAFETY_CONFIG['max_concurrent_global']})")
        print(f"💡 建议降低并发数或调整 SAFETY_CONFIG['max_concurrent_global']")
        return False
    
    return True

def signal_handler(signum, frame):
    """处理中断信号"""
    global interrupted
    print(f"\n⚠️  收到中断信号 ({signum})，正在安全退出...")
    interrupted = True
    
    if current_check_session:
        print("💾 正在保存已完成的检测结果...")
        try:
            current_check_session.commit()
            print("✅ 检测结果已保存")
        except Exception as e:
            print(f"❌ 保存失败: {e}")

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

def list_channels():
    with Session(engine) as session:
        chans = session.query(Channel).all()
        print("当前频道列表：")
        for chan in chans:
            print(f"- {chan.username}")

def add_channel(username):
    with Session(engine) as session:
        if session.query(Channel).filter_by(username=username).first():
            print("频道已存在！")
        else:
            session.add(Channel(username=username))
            session.commit()
            print(f"已添加频道：{username}")

def del_channel(username):
    with Session(engine) as session:
        chan = session.query(Channel).filter_by(username=username).first()
        if chan:
            session.delete(chan)
            session.commit()
            print(f"已删除频道：{username}")
        else:
            print("频道不存在！")

def edit_channel(old_name, new_name):
    with Session(engine) as session:
        chan = session.query(Channel).filter_by(username=old_name).first()
        if chan:
            chan.username = new_name
            session.commit()
            print(f"已将频道 {old_name} 修改为 {new_name}")
        else:
            print("原频道不存在！")

def fix_tags():
    with Session(engine) as session:
        msgs = session.query(Message).all()
        fixed = 0
        for msg in msgs:
            if msg.tags is not None and not isinstance(msg.tags, list):
                try:
                    tags_fixed = ast.literal_eval(msg.tags)
                    if isinstance(tags_fixed, list):
                        session.execute(update(Message).where(Message.id==msg.id).values(tags=tags_fixed))
                        fixed += 1
                except Exception as e:
                    print(f"ID={msg.id} tags修复失败: {e}")
        session.commit()
        print(f"已修复tags字段脏数据条数: {fixed}")

def print_help():
    print("""用法:
  python manage.py --list-channels
  python manage.py --add-channel 频道名
  python manage.py --del-channel 频道名
  python manage.py --edit-channel 旧频道名 新频道名
  python manage.py --fix-tags
  python manage.py --dedup-links-fast [batch_size]
  python manage.py --dedup-links
  python manage.py --check-links [hours] [max_concurrent]
  python manage.py --check-all-links [max_concurrent]
  python manage.py --check-period [period] [max_concurrent]
  python manage.py --link-stats
  python manage.py --show-invalid-links [check_time]
  python manage.py --show-interrupted
  python manage.py --clear-link-check-data
  python manage.py --clear-old-link-check-data [days]

🔗 链接检测命令说明:
  --check-links [hours] [max_concurrent]    检测指定时间范围内的链接 (默认24小时, 5并发)
  --check-all-links [max_concurrent]        检测所有历史链接 (默认5并发，需要确认)
  --check-period [period] [max_concurrent]  按时间段检测链接
  --link-stats                              显示链接检测统计信息
  --show-invalid-links [check_time]         显示失效链接详情 (可选指定检测时间)
  --show-interrupted                        显示中断的检测记录
  --clear-link-check-data                   清空所有链接检测数据
  --clear-old-link-check-data [days]        清空指定天数之前的检测数据 (默认30天)

📅 时间段检测格式:
  --check-period today                      检测今天
  --check-period yesterday                  检测昨天
  --check-period week                       检测最近7天
  --check-period month                      检测最近30天
  --check-period year                       检测最近365天
  --check-period 2024-01-15                检测指定日期
  --check-period 2024-01                   检测指定月份
  --check-period 2024                      检测指定年份
  --check-period 2024-01-15:2024-01-20     检测指定日期范围

🛡️ 安全机制:
  - 网盘特定限制: 不同网盘使用不同的并发数和延迟策略
  - 错误计数保护: 自动暂停错误过多的网盘检测
  - 随机延迟: 避免被识别为机器人
  - 用户确认: 大规模检测前需要用户确认
  - 安全中断: 支持 Ctrl+C 安全中断并保存结果

📊 网盘支持:
  - 百度网盘: 最大并发3, 延迟1-3秒
  - 夸克网盘: 最大并发5, 延迟0.5-2秒
  - 阿里云盘: 最大并发4, 延迟1-2.5秒
  - 115网盘: 最大并发2, 延迟2-4秒
  - 天翼云盘: 最大并发3, 延迟1-3秒
  - 123云盘: 最大并发3, 延迟1-2秒
  - UC网盘: 最大并发3, 延迟1-2秒
  - 迅雷网盘: 最大并发3, 延迟1-2秒

⚙️ 安全限制:
  - 单次检测最大链接数: 1000个
  - 全局最大并发数: 10个
  - 全量检测最大并发: 3个
  - 每个网盘最大错误数: 10个

🗂️ 数据管理:
  --clear-link-check-data                   清空所有检测数据 (需要确认)
  --clear-old-link-check-data 7             清空7天前的检测数据
  --clear-old-link-check-data 30            清空30天前的检测数据 (默认)

🔄 中断处理:
  - 检测过程中按 Ctrl+C 可以安全中断
  - 中断时会自动保存已完成的检测结果
  - 使用 --show-interrupted 查看中断记录
  - 可以重新运行检测命令完成剩余链接

💡 使用建议:
  - 首次使用建议从小规模开始 (如检测最近1小时)
  - 观察检测结果后再调整并发数
  - 如遇到大量错误，请降低并发数或暂停检测
  - 建议在非高峰期进行大规模检测
  - 定期清理旧的检测数据

📖 详细说明:
  更多详细信息请查看 README_LINK_CHECK.md 文件
""")

def parse_time_period(period_str):
    """解析时间段字符串，返回开始和结束时间"""
    from datetime import datetime, timedelta
    import re
    
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 预定义时间段
    if period_str.lower() == "today":
        start_time = today
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"今天 ({start_time.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "yesterday":
        start_time = today - timedelta(days=1)
        end_time = today
        return start_time, end_time, f"昨天 ({start_time.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "week":
        start_time = today - timedelta(days=7)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近7天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "month":
        start_time = today - timedelta(days=30)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近30天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "year":
        start_time = today - timedelta(days=365)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近365天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    # 指定日期范围 (YYYY-MM-DD:YYYY-MM-DD)
    elif ":" in period_str:
        try:
            start_date, end_date = period_str.split(":")
            start_time = datetime.strptime(start_date.strip(), "%Y-%m-%d")
            end_time = datetime.strptime(end_date.strip(), "%Y-%m-%d") + timedelta(days=1)
            return start_time, end_time, f"指定范围 ({start_date} 至 {end_date})"
        except ValueError:
            raise ValueError("日期范围格式错误，请使用 YYYY-MM-DD:YYYY-MM-DD")
    
    # 指定日期 (YYYY-MM-DD)
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', period_str):
        try:
            start_time = datetime.strptime(period_str, "%Y-%m-%d")
            end_time = start_time + timedelta(days=1)
            return start_time, end_time, f"指定日期 ({period_str})"
        except ValueError:
            raise ValueError("日期格式错误，请使用 YYYY-MM-DD")
    
    # 指定月份 (YYYY-MM)
    elif re.match(r'^\d{4}-\d{2}$', period_str):
        try:
            year, month = period_str.split("-")
            start_time = datetime(int(year), int(month), 1)
            if int(month) == 12:
                end_time = datetime(int(year) + 1, 1, 1)
            else:
                end_time = datetime(int(year), int(month) + 1, 1)
            return start_time, end_time, f"指定月份 ({period_str})"
        except ValueError:
            raise ValueError("月份格式错误，请使用 YYYY-MM")
    
    # 指定年份 (YYYY)
    elif re.match(r'^\d{4}$', period_str):
        try:
            year = int(period_str)
            start_time = datetime(year, 1, 1)
            end_time = datetime(year + 1, 1, 1)
            return start_time, end_time, f"指定年份 ({period_str})"
        except ValueError:
            raise ValueError("年份格式错误，请使用 YYYY")
    
    else:
        raise ValueError(f"不支持的时间段格式: {period_str}")

def check_links_by_period(period_str, max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """按时间段检测链接有效性"""
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    try:
        start_time, end_time, period_desc = parse_time_period(period_str)
    except ValueError as e:
        print(f"❌ 时间段格式错误: {e}")
        return
    
    print(f"🔍 开始检测 {period_desc} 的链接...")
    print(f"📅 时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取指定时间范围内的消息
    with Session(engine) as session:
        messages = session.query(Message).filter(
            Message.timestamp >= start_time,
            Message.timestamp < end_time,
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查
    if not check_safety_limits(len(all_urls), max_concurrent):
        return
    
    # 用户确认
    if not confirm_large_check(len(all_urls), max_concurrent):
        return
    
    # 开始检测
    async def run_check():
        global current_check_session, interrupted
        
        validator = LinkValidator()
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断")
            return
        
        print("🚀 开始链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 时间段: {period_desc}")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断，正在保存已完成的结果...")
            # 保存部分结果
            check_time = datetime.now()
            with Session(engine) as session:
                current_check_session = session
                # 创建统计记录（标记为中断）
                summary = validator.get_summary(results)
                stats = LinkCheckStats(
                    check_time=check_time,
                    total_messages=len(messages),
                    total_links=len(all_urls),
                    valid_links=summary['valid_links'],
                    invalid_links=summary['invalid_links'],
                    netdisk_stats=summary['netdisk_stats'],
                    check_duration=0,  # 中断时无法准确计算
                    status='interrupted'
                )
                session.add(stats)
                session.commit()
                
                # 保存详细结果
                for result in results:
                    detail = LinkCheckDetails(
                        check_time=check_time,
                        message_id=0,
                        netdisk_type=result['netdisk_type'],
                        url=result['url'],
                        is_valid=result['is_valid'],
                        response_time=result['response_time'],
                        error_reason=result['error']
                    )
                    session.add(detail)
                
                session.commit()
                current_check_session = None
            
            print("✅ 已完成的检测结果已保存")
            print_detailed_report(results, summary, show_invalid_details, max_invalid_show, period_desc + " (中断)")
            return
        
        # 正常完成检测
        check_time = datetime.now()
        start_time_check = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time_check:.2f} 秒")
        
        with Session(engine) as session:
            current_check_session = session
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time_check,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
            current_check_session = None
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show, period_desc)
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")
        if current_check_session:
            try:
                current_check_session.rollback()
                print("✅ 已回滚未完成的数据库操作")
            except:
                pass

def check_links(hours=24, max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """检测指定时间范围内的链接有效性"""
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    print(f"🔍 开始检测过去 {hours} 小时的链接...")
    
    # 获取指定时间范围内的消息
    with Session(engine) as session:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        messages = session.query(Message).filter(
            Message.timestamp >= cutoff_time,
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查
    if not check_safety_limits(len(all_urls), max_concurrent):
        return
    
    # 用户确认
    if not confirm_large_check(len(all_urls), max_concurrent):
        return
    
    # 开始检测
    async def run_check():
        validator = LinkValidator()
        
        print("🚀 开始链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 时间范围: 过去 {hours} 小时")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 保存检测结果
        check_time = datetime.now()
        start_time = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time:.2f} 秒")
        
        with Session(engine) as session:
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show)
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")

def check_all_links(max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """检测所有历史链接"""
    global current_check_session, interrupted
    
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    print("🔍 开始检测所有历史链接...")
    
    # 获取所有有链接的消息
    with Session(engine) as session:
        messages = session.query(Message).filter(
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查 - 全量检测需要更严格的限制
    if len(all_urls) > SAFETY_CONFIG['max_links_per_check']:
        print(f"❌ 全量检测链接数量 ({len(all_urls)}) 超过安全限制 ({SAFETY_CONFIG['max_links_per_check']})")
        print(f"💡 建议使用时间段检测或分批检测:")
        print(f"   - python manage.py --check-period week 3")
        print(f"   - python manage.py --check-period month 3")
        print(f"   - python manage.py --check-links 24 3")
        return
    
    if max_concurrent > 3:  # 全量检测限制更严格的并发
        print(f"❌ 全量检测并发数 ({max_concurrent}) 过高，建议使用 3 或更少")
        max_concurrent = 3
        print(f"💡 已自动调整为 {max_concurrent}")
    
    # 用户确认 - 全量检测需要强制确认
    print("\n" + "="*60)
    print("🚨 全量检测警告")
    print("="*60)
    print(f"📊 检测规模:")
    print(f"   - 链接数量: {len(all_urls)}")
    print(f"   - 最大并发: {max_concurrent}")
    print(f"   - 预计耗时: {len(all_urls) * 3 / max_concurrent / 60:.1f} - {len(all_urls) * 5 / max_concurrent / 60:.1f} 小时")
    
    print(f"\n⚠️  风险提示:")
    print(f"   - 全量检测可能触发网盘反爬虫机制")
    print(f"   - 建议在非高峰期进行")
    print(f"   - 如遇到大量错误，请立即中断")
    
    while True:
        response = input(f"\n❓ 确认开始全量检测 {len(all_urls)} 个链接? (输入 'yes' 确认): ").strip().lower()
        if response == 'yes':
            break
        elif response in ['n', 'no', '']:
            print("❌ 检测已取消")
            return
        else:
            print("请输入 'yes' 确认或 'no' 取消")
    
    # 开始检测
    async def run_check():
        global current_check_session, interrupted
        
        validator = LinkValidator()
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断")
            return
        
        print("🚀 开始全量链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 检测范围: 所有历史链接")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断，正在保存已完成的结果...")
            # 保存部分结果
            check_time = datetime.now()
            with Session(engine) as session:
                current_check_session = session
                # 创建统计记录（标记为中断）
                summary = validator.get_summary(results)
                stats = LinkCheckStats(
                    check_time=check_time,
                    total_messages=len(messages),
                    total_links=len(all_urls),
                    valid_links=summary['valid_links'],
                    invalid_links=summary['invalid_links'],
                    netdisk_stats=summary['netdisk_stats'],
                    check_duration=0,  # 中断时无法准确计算
                    status='interrupted'
                )
                session.add(stats)
                session.commit()
                
                # 保存详细结果
                for result in results:
                    detail = LinkCheckDetails(
                        check_time=check_time,
                        message_id=0,
                        netdisk_type=result['netdisk_type'],
                        url=result['url'],
                        is_valid=result['is_valid'],
                        response_time=result['response_time'],
                        error_reason=result['error']
                    )
                    session.add(detail)
                
                session.commit()
                current_check_session = None
            
            print("✅ 已完成的检测结果已保存")
            print_detailed_report(results, summary, show_invalid_details, max_invalid_show, "所有历史链接 (中断)")
            return
        
        # 正常完成检测
        check_time = datetime.now()
        start_time = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time:.2f} 秒")
        
        with Session(engine) as session:
            current_check_session = session
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
            current_check_session = None
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show, "所有历史链接")
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")
        if current_check_session:
            try:
                current_check_session.rollback()
                print("✅ 已回滚未完成的数据库操作")
            except:
                pass

def print_detailed_report(results, summary, show_invalid_details=True, max_invalid_show=10, period_desc=""):
    """打印详细的检测报告"""
    print("\n" + "="*80)
    print("📊 链接检测详细报告")
    if period_desc:
        print(f"📅 检测时段: {period_desc}")
    print("="*80)
    
    # 总体统计
    print(f"🔍 检测概况:")
    print(f"  - 总链接数: {summary['total_links']}")
    print(f"  - 有效链接: {summary['valid_links']} ✅")
    print(f"  - 无效链接: {summary['invalid_links']} ❌")
    print(f"  - 成功率: {summary['success_rate']:.1f}%")
    print(f"  - 平均响应时间: {summary['avg_response_time']:.2f}秒")
    
    # 按网盘类型统计
    print(f"\n📈 各网盘统计:")
    for netdisk, stats in summary['netdisk_stats'].items():
        success_rate = (stats['valid'] / stats['total'] * 100) if stats['total'] > 0 else 0
        status_icon = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 50 else "❌"
        print(f"  {status_icon} {netdisk}: {stats['valid']}/{stats['total']} ({success_rate:.1f}%)")
    
    # 显示失效链接详情
    if show_invalid_details:
        invalid_results = [r for r in results if not r['is_valid']]
        if invalid_results:
            print(f"\n❌ 失效链接详情 (显示前{min(max_invalid_show, len(invalid_results))}个):")
            print("-" * 80)
            
            for i, result in enumerate(invalid_results[:max_invalid_show]):
                print(f"{i+1:2d}. {result['netdisk_type']}")
                print(f"    URL: {result['url']}")
                print(f"    错误: {result['error']}")
                if result['response_time']:
                    print(f"    响应时间: {result['response_time']:.2f}秒")
                print()
            
            if len(invalid_results) > max_invalid_show:
                print(f"... 还有 {len(invalid_results) - max_invalid_show} 个失效链接")
                print("💡 使用 --link-stats 查看完整统计信息")
    
    # 性能分析
    response_times = [r['response_time'] for r in results if r['response_time'] is not None]
    if response_times:
        fast_links = sum(1 for t in response_times if t < 2.0)
        slow_links = sum(1 for t in response_times if t > 5.0)
        
        print(f"\n⚡ 性能分析:")
        print(f"  - 快速响应 (<2秒): {fast_links} 个")
        print(f"  - 正常响应 (2-5秒): {len(response_times) - fast_links - slow_links} 个")
        print(f"  - 慢速响应 (>5秒): {slow_links} 个")
    
    print("="*80)
    print("�� 检测完成！结果已保存到数据库")

def show_link_stats():
    """显示链接检测统计信息"""
    with Session(engine) as session:
        # 获取最近的检测统计
        recent_stats = session.query(LinkCheckStats).order_by(
            LinkCheckStats.check_time.desc()
        ).limit(10).all()
        
        if not recent_stats:
            print("📭 没有找到链接检测记录")
            return
        
        print("📊 最近的链接检测统计:")
        print("=" * 60)
        
        for stats in recent_stats:
            success_rate = (stats.valid_links / stats.total_links * 100) if stats.total_links > 0 else 0
            status_icon = "✅" if stats.status == 'completed' else "⚠️" if stats.status == 'interrupted' else "❓"
            print(f"检测时间: {stats.check_time}")
            print(f"状态: {status_icon} {stats.status}")
            print(f"总链接数: {stats.total_links}, 有效: {stats.valid_links}, 无效: {stats.invalid_links}")
            print(f"成功率: {success_rate:.1f}%, 耗时: {stats.check_duration:.2f}秒")
            
            if stats.netdisk_stats:
                print("各网盘统计:")
                for netdisk, data in stats.netdisk_stats.items():
                    netdisk_rate = (data['valid'] / data['total'] * 100) if data['total'] > 0 else 0
                    print(f"  - {netdisk}: {data['valid']}/{data['total']} ({netdisk_rate:.1f}%)")
            
            print("-" * 40)
        
        # 询问是否查看失效链接详情
        print("\n💡 提示: 使用 --check-links 或 --check-all-links 进行新的检测")
        print("💡 使用 --show-invalid-links [check_time] 查看特定检测的失效链接")
        print("💡 使用 --show-interrupted 查看中断的检测记录")

def show_interrupted_checks():
    """显示中断的检测记录"""
    with Session(engine) as session:
        interrupted_stats = session.query(LinkCheckStats).filter(
            LinkCheckStats.status == 'interrupted'
        ).order_by(LinkCheckStats.check_time.desc()).all()
        
        if not interrupted_stats:
            print("📭 没有找到中断的检测记录")
            return
        
        print("⚠️  中断的检测记录:")
        print("=" * 60)
        
        for stats in interrupted_stats:
            success_rate = (stats.valid_links / stats.total_links * 100) if stats.total_links > 0 else 0
            print(f"检测时间: {stats.check_time}")
            print(f"总链接数: {stats.total_links}, 有效: {stats.valid_links}, 无效: {stats.invalid_links}")
            print(f"成功率: {success_rate:.1f}%")
            print(f"状态: 中断 (可能未完成所有链接检测)")
            print("-" * 40)
        
        print("💡 建议: 可以重新运行检测命令来完成剩余的链接检测")

def clear_link_check_data(confirm=False):
    """清空所有链接检测数据"""
    with Session(engine) as session:
        # 获取当前数据统计
        stats_count = session.query(LinkCheckStats).count()
        details_count = session.query(LinkCheckDetails).count()
        
        if stats_count == 0 and details_count == 0:
            print("📭 没有找到需要清空的检测数据")
            return
        
        print(f"📊 当前检测数据统计:")
        print(f"  - 统计记录: {stats_count} 条")
        print(f"  - 详情记录: {details_count} 条")
        
        if not confirm:
            print("\n⚠️  警告: 此操作将永久删除所有链接检测数据！")
            print("💡 包括:")
            print("  - 所有检测统计记录")
            print("  - 所有链接检测详情")
            print("  - 所有中断记录")
            
            response = input("\n确认要清空所有检测数据吗？(输入 'yes' 确认): ").strip().lower()
            if response != 'yes':
                print("❌ 操作已取消")
                return
        
        try:
            # 先删除详情记录（外键依赖）
            deleted_details = session.query(LinkCheckDetails).delete()
            print(f"✅ 已删除 {deleted_details} 条详情记录")
            
            # 再删除统计记录
            deleted_stats = session.query(LinkCheckStats).delete()
            print(f"✅ 已删除 {deleted_stats} 条统计记录")
            
            session.commit()
            print("🎉 所有链接检测数据已清空！")
            
        except Exception as e:
            session.rollback()
            print(f"❌ 清空数据失败: {e}")
            return

def clear_old_link_check_data(days=30, confirm=False):
    """清空指定天数之前的检测数据"""
    with Session(engine) as session:
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 获取要删除的数据统计
        old_stats = session.query(LinkCheckStats).filter(
            LinkCheckStats.check_time < cutoff_time
        ).all()
        
        old_details = session.query(LinkCheckDetails).filter(
            LinkCheckDetails.check_time < cutoff_time
        ).all()
        
        if not old_stats and not old_details:
            print(f"📭 没有找到 {days} 天前的检测数据")
            return
        
        print(f"📊 将删除 {days} 天前的检测数据:")
        print(f"  - 统计记录: {len(old_stats)} 条")
        print(f"  - 详情记录: {len(old_details)} 条")
        print(f"  - 删除时间范围: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 之前")
        
        if not confirm:
            response = input(f"\n确认要删除 {days} 天前的检测数据吗？(输入 'yes' 确认): ").strip().lower()
            if response != 'yes':
                print("❌ 操作已取消")
                return
        
        try:
            # 先删除详情记录
            deleted_details = session.query(LinkCheckDetails).filter(
                LinkCheckDetails.check_time < cutoff_time
            ).delete()
            print(f"✅ 已删除 {deleted_details} 条详情记录")
            
            # 再删除统计记录
            deleted_stats = session.query(LinkCheckStats).filter(
                LinkCheckStats.check_time < cutoff_time
            ).delete()
            print(f"✅ 已删除 {deleted_stats} 条统计记录")
            
            session.commit()
            print(f"🎉 {days} 天前的检测数据已清空！")
            
        except Exception as e:
            session.rollback()
            print(f"❌ 删除数据失败: {e}")
            return

def show_invalid_links(check_time_str=None, limit=20):
    """显示失效链接的详细信息"""
    with Session(engine) as session:
        if check_time_str:
            # 解析时间字符串
            try:
                check_time = datetime.fromisoformat(check_time_str.replace('Z', '+00:00'))
                details = session.query(LinkCheckDetails).filter(
                    LinkCheckDetails.check_time == check_time,
                    LinkCheckDetails.is_valid == False
                ).limit(limit).all()
            except ValueError:
                print("❌ 时间格式错误，请使用 ISO 格式 (如: 2024-01-01T12:00:00)")
                return
        else:
            # 获取最近的失效链接
            details = session.query(LinkCheckDetails).filter(
                LinkCheckDetails.is_valid == False
            ).order_by(LinkCheckDetails.check_time.desc()).limit(limit).all()
        
        if not details:
            print("📭 没有找到失效链接记录")
            return
        
        print(f"❌ 失效链接详情 (显示前{len(details)}个):")
        print("=" * 80)
        
        current_check_time = None
        for i, detail in enumerate(details, 1):
            if detail.check_time != current_check_time:
                current_check_time = detail.check_time
                print(f"\n🔍 检测时间: {detail.check_time}")
                print("-" * 40)
            
            print(f"{i:2d}. {detail.netdisk_type}")
            print(f"    URL: {detail.url}")
            print(f"    错误: {detail.error_reason}")
            if detail.response_time:
                print(f"    响应时间: {detail.response_time:.2f}秒")
            print()

def extract_urls(links):
    urls = []
    if isinstance(links, str):
        # 兼容老数据
        urls.append(links)
    elif isinstance(links, dict):
        for v in links.values():
            urls.extend(extract_urls(v))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and 'url' in item:
                urls.append(item['url'])
            else:
                urls.extend(extract_urls(item))
    return urls

if __name__ == "__main__":
    if "--list-channels" in sys.argv:
        list_channels()
    elif "--add-channel" in sys.argv:
        idx = sys.argv.index("--add-channel")
        if len(sys.argv) > idx + 1:
            for name in sys.argv[idx + 1:]:
                add_channel(name.strip())
        else:
            print("请提供要添加的频道名")
    elif "--del-channel" in sys.argv:
        idx = sys.argv.index("--del-channel")
        if len(sys.argv) > idx + 1:
            del_channel(sys.argv[idx + 1])
        else:
            print("请提供要删除的频道名")
    elif "--edit-channel" in sys.argv:
        idx = sys.argv.index("--edit-channel")
        if len(sys.argv) > idx + 2:
            edit_channel(sys.argv[idx + 1], sys.argv[idx + 2])
        else:
            print("请提供旧频道名和新频道名")
    elif "--fix-tags" in sys.argv:
        # 检查并修复tags字段脏数据
        with Session(engine) as session:
            msgs = session.query(Message).all()
            fixed = 0
            for msg in msgs:
                # 如果tags不是list类型，尝试修正
                if msg.tags is not None and not isinstance(msg.tags, list):
                    try:
                        tags_fixed = ast.literal_eval(msg.tags)
                        if isinstance(tags_fixed, list):
                            session.execute(update(Message).where(Message.id==msg.id).values(tags=tags_fixed))
                            fixed += 1
                    except Exception as e:
                        print(f"ID={msg.id} tags修复失败: {e}")
            session.commit()
            print(f"已修复tags字段脏数据条数: {fixed}")
    elif "--dedup-links-fast" in sys.argv:
        # 分批流式去重，降低内存占用
        batch_size = 5000
        idx = sys.argv.index("--dedup-links-fast")
        if len(sys.argv) > idx + 1 and sys.argv[idx+1].isdigit():
            batch_size = int(sys.argv[idx+1])
        from sqlalchemy import select, text
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=engine)
        link_to_id = {}
        id_to_delete = set()
        with SessionLocal() as session:
            query = session.query(Message).order_by(Message.timestamp.desc())
            for msg in query.yield_per(batch_size):
                links = msg.links
                if isinstance(links, str):
                    try:
                        links = json.loads(links)
                    except Exception:
                        continue
                if not links:
                    continue
                urls = extract_urls(links)
                for url in urls:
                    if not isinstance(url, str):
                        continue
                    url = url.strip().lower()
                    if url in link_to_id:
                        old_id = link_to_id[url]
                        if msg.timestamp < session.get(Message, old_id).timestamp:
                            # Older message, mark for deletion
                            id_to_delete.add(msg.id)
                        else:
                            id_to_delete.add(old_id)
                            link_to_id[url] = msg.id
                    else:
                        link_to_id[url] = msg.id
            if id_to_delete:
                session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
                # 记录去重统计
                session.add(DedupStats(
                    run_time=datetime.now(),
                    inserted=len(link_to_id),
                    deleted=len(id_to_delete)
                ))
                session.commit()
                print(f"已删除重复链接消息条数: {len(id_to_delete)} 并写入统计")
                # 自动清理10小时前的去重统计数据
                session.execute(text("DELETE FROM dedup_stats WHERE run_time < NOW() - INTERVAL '10 hours'"))
                session.commit()
                print("已自动清理10小时之前的去重统计数据")
            else:
                print("没有重复链接需要删除。")

    elif "--dedup-links" in sys.argv:
        # 升级去重逻辑：相同链接且时间间隔5分钟内，优先保留网盘链接多的，否则保留最新的
        with Session(engine) as session:
            all_msgs = session.query(Message).order_by(Message.timestamp.desc()).all()
            link_to_id = {}  # {url: 最新消息id}
            id_to_delete = set()
            id_to_msg = {}  # {id: msg对象}
            for msg in all_msgs:
                links = msg.links
                if isinstance(links, str):
                    try:
                        links = json.loads(links)
                    except Exception as e:
                        print(f"ID={msg.id} links解析失败: {e}")
                        continue
                if not links:
                    continue
                for url in extract_urls(links):
                    if not isinstance(url, str):
                        continue
                    url = url.strip().lower()
                    if url in link_to_id:
                        old_id = link_to_id[url]
                        old_msg = id_to_msg[old_id]
                        time_diff = abs((msg.timestamp - old_msg.timestamp).total_seconds())
                        if time_diff < 300: # 修改为5分钟 (300秒)
                            # 5分钟内，优先保留links多的
                            if len(extract_urls(links)) > len(extract_urls(old_msg.links)):
                                id_to_delete.add(old_id)
                                link_to_id[url] = msg.id
                                id_to_msg[msg.id] = msg
                            else:
                                id_to_delete.add(msg.id)
                        else:
                            # 超过5分钟，保留最新的
                            id_to_delete.add(msg.id)
                    else:
                        link_to_id[url] = msg.id
                        id_to_msg[msg.id] = msg
            if id_to_delete:
                session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
                session.commit()
                print(f"已删除重复网盘链接的旧消息条目: {len(id_to_delete)}")
                # 自动清理10小时前的去重统计数据
                session.execute(text("DELETE FROM dedup_stats WHERE run_time < NOW() - INTERVAL '10 hours'"))
                session.commit()
                print("已自动清理10小时之前的去重统计数据")
            else:
                print("没有需要删除的重复网盘链接消息。")
    elif "--check-links" in sys.argv:
        # 链接检测功能
        hours = 24  # 默认检测24小时
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-links")
        if len(sys.argv) > idx + 1:
            try:
                hours = int(sys.argv[idx + 1])
            except ValueError:
                print("❌ 时间范围必须是数字")
                sys.exit(1)
        
        if len(sys.argv) > idx + 2:
            try:
                max_concurrent = int(sys.argv[idx + 2])
            except ValueError:
                print("❌ 并发数必须是数字")
                sys.exit(1)
        
        check_links(hours, max_concurrent)
        
    elif "--check-all-links" in sys.argv:
        # 检测所有历史链接
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-all-links")
        if len(sys.argv) > idx + 1:
            try:
                max_concurrent = int(sys.argv[idx + 1])
            except ValueError:
                print("❌ 并发数必须是数字")
                sys.exit(1)
        
        check_all_links(max_concurrent)
        
    elif "--check-period" in sys.argv:
        # 按时间段检测链接
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-period")
        if len(sys.argv) > idx + 1:
            period_str = sys.argv[idx + 1]
            
            # 检查是否有并发数参数
            if len(sys.argv) > idx + 2:
                try:
                    max_concurrent = int(sys.argv[idx + 2])
                except ValueError:
                    print("❌ 并发数必须是数字")
                    sys.exit(1)
            
            check_links_by_period(period_str, max_concurrent)
        else:
            print("请提供时间段参数 (如: today, yesterday, week, month, year, YYYY-MM-DD, YYYY-MM, YYYY, YYYY-MM-DD:YYYY-MM-DD)")
        
    elif "--link-stats" in sys.argv:
        # 显示链接检测统计
        show_link_stats()
        
    elif "--show-invalid-links" in sys.argv:
        # 显示失效链接详情
        idx = sys.argv.index("--show-invalid-links")
        if len(sys.argv) > idx + 1:
            show_invalid_links(sys.argv[idx + 1])
        else:
            show_invalid_links()
        
    elif "--show-interrupted" in sys.argv:
        # 显示中断的检测记录
        show_interrupted_checks()
        
    elif "--clear-link-check-data" in sys.argv:
        # 清空所有链接检测数据
        clear_link_check_data()

    elif "--clear-old-link-check-data" in sys.argv:
        # 清空指定天数之前的检测数据
        days = 30  # 默认30天
        idx = sys.argv.index("--clear-old-link-check-data")
        if len(sys.argv) > idx + 1 and sys.argv[idx+1].isdigit():
            days = int(sys.argv[idx+1])
        clear_old_link_check_data(days)
        
    else:
        print_help() 