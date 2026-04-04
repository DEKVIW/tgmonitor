/**
 * API客户端配置
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'
import { API_BASE_URL, TOKEN_KEY } from './constants'
import { LOGIN_PATH, isPathMatch } from './routes'
import { message } from 'antd'

const isLinkCheckTaskPoll404 = (error: AxiosError): boolean => {
  const status = error.response?.status
  const method = error.config?.method?.toLowerCase()
  const url = error.config?.url || ''

  return (
    status === 404 &&
    method === 'get' &&
    (
      /^\/admin\/link-check\/tasks\/[^/]+$/.test(url) ||
      url === '/admin/link-check/active'
    )
  )
}

// 创建axios实例
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：添加Token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理错误
apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  (error: AxiosError) => {
    if (isLinkCheckTaskPoll404(error)) {
      return Promise.reject(error)
    }

    if (error.response) {
      const status = error.response.status
      const data = error.response.data as any

      switch (status) {
        case 401:
          // 未授权，清除token并跳转到登录页
          localStorage.removeItem(TOKEN_KEY)
          if (!isPathMatch(window.location.pathname, LOGIN_PATH)) {
            window.location.href = LOGIN_PATH
            message.error('登录已过期，请重新登录')
          }
          break
        case 403:
          message.error('没有权限访问此资源')
          break
        case 404:
          message.error('请求的资源不存在')
          break
        case 500:
          message.error(data?.detail || '服务器内部错误')
          break
        default:
          message.error(data?.detail || `请求失败: ${status}`)
      }
    } else if (error.request) {
      message.error('网络错误，请检查网络连接')
    } else {
      message.error('请求配置错误')
    }

    return Promise.reject(error)
  }
)

export default apiClient

