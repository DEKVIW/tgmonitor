#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用链接有效性检测模块
支持多种检测方式和网盘特殊处理
"""

import asyncio
import aiohttp
import re
import time
import random
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse
import validators

class LinkValidator:
    """链接有效性检测器"""
    
    def __init__(self):
        # 网盘特定的失效关键词
        self.netdisk_invalid_patterns = {
            "百度网盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"分享链接已失效",
                r"文件已被删除", r"分享已取消", r"访问被拒绝"
            ],
            "夸克网盘": [
                r"文件不存在或已被删除", r"分享链接已失效", r"文件已被删除",
                r"分享已过期", r"访问被拒绝"
            ],
            "阿里云盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ],
            "115网盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ],
            "天翼云盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ],
            "123云盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ],
            "UC网盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ],
            "迅雷网盘": [
                r"文件不存在", r"分享已失效", r"链接已过期", r"文件已被删除"
            ]
        }
        
        # 通用失效关键词
        self.general_invalid_patterns = [
            r"页面不存在", r"访问被拒绝", r"服务器错误",
            r"页面未找到", r"无法访问", r"连接超时",
            r"404\s*错误", r"404\s*页面", r"404\s*not\s*found"
        ]
        
        # 网盘特定的请求限制
        self.netdisk_limits = {
            "百度网盘": {"max_concurrent": 3, "delay_range": (1, 3)},
            "夸克网盘": {"max_concurrent": 5, "delay_range": (0.5, 2)},
            "阿里云盘": {"max_concurrent": 4, "delay_range": (1, 2.5)},
            "115网盘": {"max_concurrent": 2, "delay_range": (2, 4)},
            "天翼云盘": {"max_concurrent": 3, "delay_range": (1, 3)},
            "123云盘": {"max_concurrent": 3, "delay_range": (1, 2)},
            "UC网盘": {"max_concurrent": 3, "delay_range": (1, 2)},
            "迅雷网盘": {"max_concurrent": 3, "delay_range": (1, 2)},
            "未知网盘": {"max_concurrent": 2, "delay_range": (2, 4)}
        }
        
        # 请求头 - 模拟真实浏览器
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',  # 移除br编码，避免Brotli问题
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        
        # 错误计数和限制
        self.error_counts = {}
        self.max_errors_per_netdisk = 10  # 每个网盘最多允许10个连续错误
        
        # 重试机制配置
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2  # 重试间隔（秒）
        
        # 可重试的错误类型
        self.retryable_errors = [
            '网络超时', '网络错误', '状态码错误', '检测异常'
        ]
        
        # 不可重试的错误类型
        self.non_retryable_errors = [
            '格式错误', '网盘链接失效', '页面错误', '网盘限制'
        ]
    
    def validate_url_format(self, url: str) -> bool:
        """快速验证URL格式"""
        try:
            parsed = urlparse(url)
            # 检查基本格式：必须有scheme和netloc
            return bool(parsed.scheme and parsed.netloc and 
                       parsed.scheme in ('http', 'https'))
        except Exception:
            return False
    
    def get_netdisk_type(self, url: str) -> str:
        """根据URL判断网盘类型"""
        domain = urlparse(url).netloc.lower()
        
        netdisk_domains = {
            "百度网盘": ["pan.baidu.com"],
            "夸克网盘": ["pan.quark.cn"],
            "阿里云盘": ["www.alipan.com", "www.aliyundrive.com"],
            "115网盘": ["115.com", "115cdn.com"],
            "天翼云盘": ["cloud.189.cn"],
            "123云盘": ["www.123684.com", "www.123pan.com"],
            "UC网盘": ["drive.uc.cn"],
            "迅雷网盘": ["pan.xunlei.com"]
        }
        
        for netdisk, domains in netdisk_domains.items():
            if any(domain in d for d in domains):
                return netdisk
        
        return "未知网盘"
    
    def get_netdisk_limits(self, netdisk_type: str) -> Dict:
        """获取网盘特定的限制配置"""
        return self.netdisk_limits.get(netdisk_type, self.netdisk_limits["未知网盘"])
    
    async def check_single_link(self, url: str, timeout: int = 15) -> Dict:
        """检测单个链接的有效性"""
        result = {
            'url': url,
            'netdisk_type': self.get_netdisk_type(url),
            'is_valid': False,
            'status_code': None,
            'response_time': None,
            'error': None,
            'reason': None
        }
        
        netdisk_type = result['netdisk_type']
        
        # 检查错误计数
        if self.error_counts.get(netdisk_type, 0) >= self.max_errors_per_netdisk:
            result['error'] = f"网盘 {netdisk_type} 错误次数过多，暂停检测"
            result['reason'] = "网盘限制"
            return result
        
        # 首先验证URL格式
        try:
            parsed = urlparse(url)
            if not (parsed.scheme and parsed.netloc and parsed.scheme in ('http', 'https')):
                result['error'] = "URL格式无效"
                result['reason'] = "格式错误"
                return result
        except Exception:
            result['error'] = "URL格式无效"
            result['reason'] = "格式错误"
            return result
        
        # 添加随机延迟
        limits = self.get_netdisk_limits(netdisk_type)
        delay = random.uniform(*limits['delay_range'])
        await asyncio.sleep(delay)
        
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, 
                    headers=self.headers, 
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True
                ) as response:
                    result['response_time'] = time.time() - start_time
                    result['status_code'] = response.status
                    
                    # 检查HTTP状态码
                    if response.status != 200:
                        result['error'] = f"HTTP {response.status}"
                        result['reason'] = "状态码错误"
                        # 增加错误计数
                        self.error_counts[netdisk_type] = self.error_counts.get(netdisk_type, 0) + 1
                        return result
                    
                    # 获取页面内容
                    content = await response.text()
                    
                    # 检查网盘特定的失效模式
                    if netdisk_type in self.netdisk_invalid_patterns:
                        patterns = self.netdisk_invalid_patterns[netdisk_type]
                        for pattern in patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                result['error'] = f"网盘显示失效: {pattern}"
                                result['reason'] = "网盘链接失效"
                                return result
                    
                    # 检查通用失效模式
                    for pattern in self.general_invalid_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            result['error'] = f"页面显示错误: {pattern}"
                            result['reason'] = "页面错误"
                            return result
                    
                    # 如果通过所有检查，认为链接有效
                    result['is_valid'] = True
                    result['reason'] = "链接有效"
                    # 重置错误计数
                    self.error_counts[netdisk_type] = 0
                    
        except asyncio.TimeoutError:
            result['error'] = "请求超时"
            result['reason'] = "网络超时"
            self.error_counts[netdisk_type] = self.error_counts.get(netdisk_type, 0) + 1
        except aiohttp.ClientError as e:
            result['error'] = f"网络错误: {str(e)}"
            result['reason'] = "网络错误"
            self.error_counts[netdisk_type] = self.error_counts.get(netdisk_type, 0) + 1
        except Exception as e:
            result['error'] = f"未知错误: {str(e)}"
            result['reason'] = "未知错误"
            self.error_counts[netdisk_type] = self.error_counts.get(netdisk_type, 0) + 1
        
        return result
    
    def is_retryable_error(self, result: Dict) -> bool:
        """判断错误是否可重试"""
        return result.get('reason') in self.retryable_errors
    
    async def retry_failed_links(self, failed_results: List[Dict]) -> List[Dict]:
        """重试失败的链接"""
        if not failed_results:
            return []
        
        retryable_results = [r for r in failed_results if self.is_retryable_error(r)]
        if not retryable_results:
            return failed_results
        
        print(f"🔄 开始重试 {len(retryable_results)} 个可重试的链接...")
        
        # 按网盘类型分组重试
        netdisk_groups = {}
        for result in retryable_results:
            netdisk_type = result['netdisk_type']
            if netdisk_type not in netdisk_groups:
                netdisk_groups[netdisk_type] = []
            netdisk_groups[netdisk_type].append(result['url'])
        
        retry_results = []
        
        for netdisk_type, urls in netdisk_groups.items():
            print(f"🔄 重试 {netdisk_type}: {len(urls)} 个链接")
            
            # 重试每个链接
            for url in urls:
                for attempt in range(1, self.max_retries + 1):
                    print(f"  🔄 重试 {url} (第{attempt}次)")
                    
                    # 重试前等待
                    await asyncio.sleep(self.retry_delay)
                    
                    # 重新检测
                    new_result = await self.check_single_link(url)
                    
                    # 如果成功或不可重试，停止重试
                    if new_result['is_valid'] or not self.is_retryable_error(new_result):
                        retry_results.append(new_result)
                        break
                    
                    # 最后一次重试
                    if attempt == self.max_retries:
                        retry_results.append(new_result)
                        print(f"    ❌ 重试{self.max_retries}次后仍然失败")
        
        # 合并结果：重试成功的替换原结果，重试失败的保持原结果
        final_results = []
        retry_urls = {r['url'] for r in retry_results}
        
        for result in failed_results:
            if result['url'] in retry_urls:
                # 找到重试结果
                retry_result = next(r for r in retry_results if r['url'] == result['url'])
                final_results.append(retry_result)
            else:
                # 不可重试的错误，保持原结果
                final_results.append(result)
        
        return final_results

    async def check_multiple_links(self, urls: List[str], max_concurrent: int = 5) -> List[Dict]:
        """并发检测多个链接 - 改进版本，支持重试"""
        # 按网盘类型分组
        netdisk_groups = {}
        for url in urls:
            netdisk_type = self.get_netdisk_type(url)
            if netdisk_type not in netdisk_groups:
                netdisk_groups[netdisk_type] = []
            netdisk_groups[netdisk_type].append(url)
        
        print(f"📊 按网盘类型分组: {len(netdisk_groups)} 种网盘")
        for netdisk, urls_list in netdisk_groups.items():
            limits = self.get_netdisk_limits(netdisk)
            print(f"  - {netdisk}: {len(urls_list)} 个链接, 最大并发 {limits['max_concurrent']}, 延迟 {limits['delay_range']}秒")
        
        all_results = []
        
        # 按网盘类型分别处理
        for netdisk_type, netdisk_urls in netdisk_groups.items():
            limits = self.get_netdisk_limits(netdisk_type)
            netdisk_concurrent = min(limits['max_concurrent'], max_concurrent)
            
            print(f"🔍 开始检测 {netdisk_type} ({len(netdisk_urls)} 个链接, 并发 {netdisk_concurrent})")
            
            # 为每个网盘创建信号量
            semaphore = asyncio.Semaphore(netdisk_concurrent)
            
            async def check_with_semaphore(url):
                async with semaphore:
                    return await self.check_single_link(url)
            
            # 检测当前网盘的链接
            tasks = [check_with_semaphore(url) for url in netdisk_urls]
            netdisk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理异常结果
            for i, result in enumerate(netdisk_results):
                if isinstance(result, Exception):
                    netdisk_results[i] = {
                        'url': netdisk_urls[i],
                        'netdisk_type': netdisk_type,
                        'is_valid': False,
                        'status_code': None,
                        'response_time': None,
                        'error': str(result),
                        'reason': "检测异常"
                    }
            
            all_results.extend(netdisk_results)
            
            # 检查是否达到错误限制
            if self.error_counts.get(netdisk_type, 0) >= self.max_errors_per_netdisk:
                print(f"⚠️  {netdisk_type} 错误次数过多，跳过剩余链接")
                # 为剩余链接添加跳过标记
                remaining_count = len(netdisk_urls) - len(netdisk_results)
                for _ in range(remaining_count):
                    all_results.append({
                        'url': 'skipped',
                        'netdisk_type': netdisk_type,
                        'is_valid': False,
                        'status_code': None,
                        'response_time': None,
                        'error': f"{netdisk_type} 错误次数过多，跳过检测",
                        'reason': "网盘限制"
                    })
        
        # 第一轮检测完成，开始重试失败的链接
        failed_results = [r for r in all_results if not r['is_valid']]
        if failed_results:
            print(f"\n📊 第一轮检测完成，发现 {len(failed_results)} 个失败链接")
            
            # 重试失败的链接
            retry_results = await self.retry_failed_links(failed_results)
            
            # 更新结果
            final_results = []
            failed_urls = {r['url'] for r in failed_results}
            
            for result in all_results:
                if result['url'] in failed_urls:
                    # 找到重试结果
                    retry_result = next(r for r in retry_results if r['url'] == result['url'])
                    final_results.append(retry_result)
                else:
                    # 成功的链接，保持原结果
                    final_results.append(result)
            
            return final_results
        
        return all_results
    
    def get_summary(self, results: List[Dict]) -> Dict:
        """获取检测结果摘要"""
        total = len(results)
        valid = sum(1 for r in results if r['is_valid'])
        invalid = total - valid
        
        # 按网盘类型统计
        netdisk_stats = {}
        for result in results:
            netdisk = result['netdisk_type']
            if netdisk not in netdisk_stats:
                netdisk_stats[netdisk] = {'total': 0, 'valid': 0, 'invalid': 0}
            
            netdisk_stats[netdisk]['total'] += 1
            if result['is_valid']:
                netdisk_stats[netdisk]['valid'] += 1
            else:
                netdisk_stats[netdisk]['invalid'] += 1
        
        # 计算平均响应时间
        response_times = [r['response_time'] for r in results if r['response_time'] is not None]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'total_links': total,
            'valid_links': valid,
            'invalid_links': invalid,
            'success_rate': (valid / total * 100) if total > 0 else 0,
            'avg_response_time': avg_response_time,
            'netdisk_stats': netdisk_stats
        }

# 使用示例
async def main():
    """使用示例"""
    validator = LinkValidator()
    
    # 测试链接
    test_urls = [
        "https://pan.quark.cn/s/1035a75ca667#/list/share",
        "https://pan.baidu.com/share/init?surl=kq2X2n1Yn_to_ZS41qYJFw&pwd=t6ic",
        "https://www.alipan.com/s/q2QX6AGdJm5"
    ]
    
    print("开始检测链接...")
    results = await validator.check_multiple_links(test_urls)
    
    # 打印结果
    for result in results:
        status = "✅" if result['is_valid'] else "❌"
        print(f"{status} {result['netdisk_type']}: {result['url']}")
        print(f"   状态: {result['reason']}")
        if result['response_time']:
            print(f"   响应时间: {result['response_time']:.2f}秒")
        if result['error']:
            print(f"   错误: {result['error']}")
        print()
    
    # 打印摘要
    summary = validator.get_summary(results)
    print(f"检测完成: {summary['valid_links']}/{summary['total_links']} 个链接有效")
    print(f"成功率: {summary['success_rate']:.1f}%")
    print(f"平均响应时间: {summary['avg_response_time']:.2f}秒")

if __name__ == "__main__":
    asyncio.run(main()) 