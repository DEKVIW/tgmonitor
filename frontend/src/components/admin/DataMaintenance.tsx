/**
 * 数据维护组件
 */

import { useState } from 'react'
import {
  Card,
  Button,
  message,
  Popconfirm,
  InputNumber,
  Space,
  Typography,
  Alert,
} from 'antd'
import {
  ToolOutlined,
  ReloadOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import {
  fixTags,
  dedupLinks,
  clearLinkCheckData,
  clearOldLinkCheckData,
} from '@/api/admin'
import { MaintenanceResult } from '@/types/admin'

const { Text, Paragraph } = Typography

const DataMaintenance = () => {
  const [fixTagsLoading, setFixTagsLoading] = useState(false)
  const [dedupLinksLoading, setDedupLinksLoading] = useState(false)
  const [clearDataLoading, setClearDataLoading] = useState(false)
  const [clearOldDataLoading, setClearOldDataLoading] = useState(false)
  const [days, setDays] = useState(30)

  const handleFixTags = async () => {
    setFixTagsLoading(true)
    try {
      const result: MaintenanceResult = await fixTags()
      if (result.success) {
        message.success(`修复成功！共修复 ${result.fixed_count || 0} 条数据`)
        if (result.errors && result.errors.length > 0) {
          message.warning(`部分数据修复失败: ${result.errors.join(', ')}`)
        }
      } else {
        message.error(result.error || '修复失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '修复Tags失败')
    } finally {
      setFixTagsLoading(false)
    }
  }

  const handleDedupLinks = async () => {
    setDedupLinksLoading(true)
    try {
      const result: MaintenanceResult = await dedupLinks()
      if (result.success) {
        message.success(`去重成功！共删除 ${result.deleted_count || 0} 条重复消息`)
      } else {
        message.error(result.error || '去重失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '链接去重失败')
    } finally {
      setDedupLinksLoading(false)
    }
  }

  const handleClearLinkCheckData = async () => {
    setClearDataLoading(true)
    try {
      const result: MaintenanceResult = await clearLinkCheckData()
      if (result.success) {
        message.success(
          `清空成功！共删除 ${result.deleted_details || 0} 条详细记录，${result.deleted_stats || 0} 条统计记录`
        )
      } else {
        message.error(result.error || '清空失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清空链接检测数据失败')
    } finally {
      setClearDataLoading(false)
    }
  }

  const handleClearOldLinkCheckData = async () => {
    setClearOldDataLoading(true)
    try {
      const result: MaintenanceResult = await clearOldLinkCheckData({ days })
      if (result.success) {
        message.success(
          `清空成功！共删除 ${result.deleted_details || 0} 条详细记录，${result.deleted_stats || 0} 条统计记录`
        )
      } else {
        message.error(result.error || '清空失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清空旧链接检测数据失败')
    } finally {
      setClearOldDataLoading(false)
    }
  }

  return (
    <div className="data-maintenance">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card title="🔧 数据修复">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Button
                type="primary"
                icon={<ToolOutlined />}
                onClick={handleFixTags}
                loading={fixTagsLoading}
              >
                修复Tags脏数据
              </Button>
              <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                修复消息tags字段中的脏数据，将字符串格式转换为list格式
              </Paragraph>
            </div>

            <div>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleDedupLinks}
                loading={dedupLinksLoading}
              >
                链接去重
              </Button>
              <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                去除重复的链接记录。相同链接且时间间隔5分钟内，优先保留网盘链接多的，否则保留最新的
              </Paragraph>
            </div>
          </Space>
        </Card>

        <Card title="🗑️ 数据清理">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Popconfirm
                title="确定要清空所有链接检测数据吗？"
                description="此操作不可恢复，将删除所有链接检测记录"
                onConfirm={handleClearLinkCheckData}
                okText="确定"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={clearDataLoading}
                >
                  清空链接检测数据
                </Button>
              </Popconfirm>
              <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                清空所有链接检测记录
                <Alert
                  message="危险操作"
                  description="此操作会删除所有链接检测数据，请谨慎操作"
                  type="warning"
                  showIcon
                  style={{ marginTop: 8 }}
                />
              </Paragraph>
            </div>

            <div>
              <Space>
                <InputNumber
                  min={1}
                  max={365}
                  value={days}
                  onChange={(value) => setDays(value || 30)}
                />
                <Text>天</Text>
                <Popconfirm
                  title={`确定要清空 ${days} 天前的链接检测数据吗？`}
                  description={`将删除 ${days} 天之前的所有链接检测记录`}
                  onConfirm={handleClearOldLinkCheckData}
                  okText="确定"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                >
                  <Button
                    danger
                    icon={<DeleteOutlined />}
                    loading={clearOldDataLoading}
                  >
                    清空旧数据
                  </Button>
                </Popconfirm>
              </Space>
              <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                清空指定天数之前的链接检测数据
              </Paragraph>
            </div>
          </Space>
        </Card>
      </Space>
    </div>
  )
}

export default DataMaintenance

