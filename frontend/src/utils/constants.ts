/**
 * 常量定义
 */

// API基础URL（兼容非 vite 类型环境）
const env = (import.meta as any).env || {}
export const API_BASE_URL = env.VITE_API_BASE_URL || '/api'

// Token存储键名
export const TOKEN_KEY = 'tg_monitor_token'

// 时间范围选项
export const TIME_RANGES = [
  { label: '最近1小时', value: '最近1小时' },
  { label: '最近24小时', value: '最近24小时' },
  { label: '最近7天', value: '最近7天' },
  { label: '最近30天', value: '最近30天' },
  { label: '全部', value: '全部' },
] as const

// 每页显示选项
export const PAGE_SIZES = [50, 100, 200] as const

// 网盘类型
export const NETDISK_TYPES = [
  '夸克网盘',
  '阿里云盘',
  '百度网盘',
  '115网盘',
  '天翼云盘',
  '123云盘',
  'UC网盘',
  '迅雷',
] as const

// 网盘图标映射
export const NETDISK_ICONS: Record<string, string> = {
  '夸克网盘': '⚡',
  '阿里云盘': '🛡️',
  '百度网盘': '🔍',
  '115网盘': '💎',
  '天翼云盘': '🌊',
  '123云盘': '🎯',
  'UC网盘': '🌍',
  '迅雷': '🚀',
}

// 网盘颜色映射
export const NETDISK_COLORS: Record<string, string> = {
  '夸克': '#4E79A7',
  '阿里': '#F28E2B',
  '百度': '#76B7B2',
  '115': '#59A14F',
  '天翼': '#E15759',
  '123': '#B07AA1',
  'UC': '#EDC948',
  '迅雷': '#7F7F7F',
}

