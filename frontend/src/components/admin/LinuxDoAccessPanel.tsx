import { useEffect, useMemo, useRef, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { LockOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'

import {
  createLinuxDoBatch,
  getLinuxDoConfig,
  updateLinuxDoBatch,
  updateLinuxDoConfig,
} from '@/api/admin'
import type {
  LinuxDoBatchResponse,
  LinuxDoBatchUpsert,
  LinuxDoConfigResponse,
  LinuxDoConfigUpdate,
} from '@/types/admin'

import './LinuxDoAccessPanel.css'

const { Text } = Typography

type ConfigFormValues = {
  enabled: boolean
  allow_new_accounts: boolean
  client_id: string
  client_secret: string
  clear_client_secret: boolean
}

type BatchFormValues = {
  batch_name: string
  is_enabled: boolean
  max_accounts: number
  default_role: 'admin' | 'user'
  validity_mode: 'permanent' | 'duration' | 'fixed_at'
  validity_unit?: 'day' | 'month' | 'year'
  validity_value?: number
  fixed_expires_at?: Dayjs | null
  starts_at?: Dayjs | null
  ends_at?: Dayjs | null
  notes?: string
}

const statusColorMap: Record<string, string> = {
  open: 'success',
  full: 'warning',
  scheduled: 'processing',
  ended: 'default',
  paused: 'default',
  disabled: 'default',
}

const modeColorMap: Record<string, string> = {
  hidden: 'default',
  existing_only: 'processing',
  open: 'success',
}

const modeLabelMap: Record<string, string> = {
  hidden: '已隐藏',
  existing_only: '仅已绑定可登录',
  open: '开放接入',
}

const batchStatusLabelMap: Record<string, string> = {
  open: '开放中',
  full: '名额已满',
  scheduled: '待开始',
  ended: '已结束',
  paused: '已暂停',
  disabled: '已关闭',
}

const parseDateTime = (value?: string | null) => {
  if (!value) {
    return null
  }
  const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(value)
  return dayjs(hasTimezone ? value : `${value}Z`)
}

const formatDateTime = (value?: string | null) => {
  const parsed = parseDateTime(value)
  return parsed ? parsed.format('YYYY-MM-DD HH:mm') : '-'
}

const formatValidity = (batch: LinuxDoBatchResponse) => {
  if (batch.validity_mode === 'permanent') {
    return '永久'
  }
  if (batch.validity_mode === 'fixed_at') {
    return `固定到期 ${formatDateTime(batch.fixed_expires_at)}`
  }
  return `${batch.validity_value || 1}${batch.validity_unit === 'day' ? '天' : batch.validity_unit === 'year' ? '年' : '个月'}`
}

const buildBatchFormValues = (batch?: LinuxDoBatchResponse | null): BatchFormValues => ({
  batch_name: batch?.batch_name || '',
  is_enabled: batch?.is_enabled ?? true,
  max_accounts: batch?.max_accounts || 50,
  default_role: (batch?.default_role as 'admin' | 'user') || 'user',
  validity_mode: (batch?.validity_mode as 'permanent' | 'duration' | 'fixed_at') || 'duration',
  validity_unit: (batch?.validity_unit as 'day' | 'month' | 'year' | undefined) || 'month',
  validity_value: batch?.validity_value || 1,
  fixed_expires_at: parseDateTime(batch?.fixed_expires_at),
  starts_at: parseDateTime(batch?.starts_at),
  ends_at: parseDateTime(batch?.ends_at),
  notes: batch?.notes || '',
})

const LinuxDoAccessPanel = () => {
  const [loading, setLoading] = useState(false)
  const [configSaving, setConfigSaving] = useState(false)
  const [batchSaving, setBatchSaving] = useState(false)
  const [config, setConfig] = useState<LinuxDoConfigResponse | null>(null)
  const [editingBatch, setEditingBatch] = useState<LinuxDoBatchResponse | null>(null)
  const [configForm] = Form.useForm<ConfigFormValues>()
  const [batchForm] = Form.useForm<BatchFormValues>()
  const batchEditorRef = useRef<HTMLDivElement | null>(null)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const result = await getLinuxDoConfig()
      setConfig(result)
      configForm.setFieldsValue({
        enabled: result.enabled,
        allow_new_accounts: result.allow_new_accounts,
        client_id: result.client_id || '',
        client_secret: '',
        clear_client_secret: false,
      })
      if (!editingBatch) {
        batchForm.setFieldsValue(buildBatchFormValues(result.current_batch))
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载 LinuxDo 配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadConfig()
  }, [])

  const currentBatch = config?.current_batch || null

  const summaryItems = useMemo(() => {
    if (!config) {
      return []
    }
    return [
      { label: '入口状态', value: modeLabelMap[config.login_mode] || config.login_mode, tone: config.login_mode },
      { label: '已绑定账号', value: `${config.bound_account_count}`, tone: 'default' },
      {
        label: '当前批次',
        value: currentBatch ? currentBatch.batch_name : '未设置',
        tone: currentBatch?.status || 'default',
      },
      {
        label: '剩余名额',
        value:
          currentBatch?.remaining_accounts === null || currentBatch?.remaining_accounts === undefined
            ? '不限'
            : `${currentBatch.remaining_accounts}`,
        tone: currentBatch?.status || 'default',
      },
    ]
  }, [config, currentBatch])

  const handleSaveConfig = async (values: ConfigFormValues) => {
    setConfigSaving(true)
    try {
      const payload: LinuxDoConfigUpdate = {
        enabled: values.enabled,
        allow_new_accounts: values.allow_new_accounts,
        client_id: values.client_id.trim(),
        client_secret: values.client_secret.trim(),
        clear_client_secret: values.clear_client_secret,
      }
      const updated = await updateLinuxDoConfig(payload)
      setConfig(updated)
      configForm.setFieldsValue({
        enabled: updated.enabled,
        allow_new_accounts: updated.allow_new_accounts,
        client_id: updated.client_id || '',
        client_secret: '',
        clear_client_secret: false,
      })
      message.success('LinuxDo 登录配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存 LinuxDo 配置失败')
    } finally {
      setConfigSaving(false)
    }
  }

  const handleEditBatch = (batch: LinuxDoBatchResponse) => {
    setEditingBatch(batch)
    batchForm.setFieldsValue(buildBatchFormValues(batch))
    window.requestAnimationFrame(() => {
      batchEditorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  const handleResetBatch = () => {
    setEditingBatch(null)
    batchForm.setFieldsValue(buildBatchFormValues())
  }

  const handleSaveBatch = async (values: BatchFormValues) => {
    setBatchSaving(true)
    try {
      const payload: LinuxDoBatchUpsert = {
        batch_name: values.batch_name.trim(),
        is_enabled: values.is_enabled,
        max_accounts: Number(values.max_accounts || 1),
        default_role: values.default_role,
        validity_mode: values.validity_mode,
        validity_unit: values.validity_mode === 'duration' ? values.validity_unit || 'month' : null,
        validity_value: values.validity_mode === 'duration' ? Number(values.validity_value || 1) : null,
        fixed_expires_at:
          values.validity_mode === 'fixed_at' && values.fixed_expires_at
            ? values.fixed_expires_at.toISOString()
            : null,
        starts_at: values.starts_at ? values.starts_at.toISOString() : null,
        ends_at: values.ends_at ? values.ends_at.toISOString() : null,
        notes: values.notes?.trim() || '',
      }
      const updated = editingBatch
        ? await updateLinuxDoBatch(editingBatch.id, payload)
        : await createLinuxDoBatch(payload)

      setConfig(updated)
      setEditingBatch(updated.current_batch && editingBatch ? updated.current_batch : null)
      if (editingBatch) {
        const refreshed =
          updated.recent_batches.find((item) => item.id === editingBatch.id) || updated.current_batch || null
        setEditingBatch(refreshed)
        batchForm.setFieldsValue(buildBatchFormValues(refreshed))
      } else {
        handleResetBatch()
      }
      message.success(editingBatch ? '批次已更新' : '批次已创建')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存批次失败')
    } finally {
      setBatchSaving(false)
    }
  }

  const columns: ColumnsType<LinuxDoBatchResponse> = [
    {
      title: '批次',
      key: 'batch_name',
      render: (_, record) => (
        <div className="linuxdo-access-batch-name">
          <span>{record.batch_name}</span>
          <small>{record.batch_code}</small>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => (
        <Tag color={statusColorMap[value] || 'default'}>{batchStatusLabelMap[value] || value}</Tag>
      ),
    },
    {
      title: '名额',
      key: 'seats',
      render: (_, record) => {
        const total = record.max_accounts ?? 0
        return `${record.allocated_accounts}/${total || '不限'}`
      },
    },
    {
      title: '默认权限',
      dataIndex: 'default_role',
      key: 'default_role',
      render: (value: string) => (value === 'admin' ? '管理员' : '普通用户'),
    },
    {
      title: '有效期',
      key: 'validity',
      render: (_, record) => formatValidity(record),
    },
    {
      title: '开放时段',
      key: 'window',
      render: (_, record) => {
        if (!record.starts_at && !record.ends_at) {
          return '不限'
        }
        return `${formatDateTime(record.starts_at)} - ${formatDateTime(record.ends_at)}`
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button type="link" onClick={() => handleEditBatch(record)}>
          编辑
        </Button>
      ),
    },
  ]

  return (
    <Card className="linuxdo-access-card" variant="borderless" loading={loading}>
      <div className="linuxdo-access-header">
        <div>
          <Text strong>LinuxDo 登录</Text>
          <div className="linuxdo-access-summary">
            这里控制登录按钮是否显示、是否允许新用户接入，以及每一批开放名额的角色和有效期。
          </div>
        </div>
        <Space wrap>
          <Tag color={modeColorMap[config?.login_mode || 'hidden'] || 'default'}>
            {modeLabelMap[config?.login_mode || 'hidden'] || '已隐藏'}
          </Tag>
          <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()}>
            刷新
          </Button>
        </Space>
      </div>

      <div className="linuxdo-access-overview">
        {summaryItems.map((item) => (
          <div key={item.label} className="linuxdo-access-overview-item">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>

      <div className="linuxdo-access-layout">
        <section className="linuxdo-access-section">
          <div className="linuxdo-access-section-head">
            <Text strong>入口与凭据</Text>
            <span className="linuxdo-access-section-copy">
              关闭入口后，登录页不会显示 LinuxDo 按钮；关闭新用户接入后，老绑定账号仍可继续登录。
            </span>
          </div>

          <Form<ConfigFormValues>
            form={configForm}
            layout="vertical"
            onFinish={(values) => void handleSaveConfig(values)}
            initialValues={{
              enabled: false,
              allow_new_accounts: false,
              client_id: '',
              client_secret: '',
              clear_client_secret: false,
            }}
          >
            <div className="linuxdo-access-form-grid">
              <Form.Item name="enabled" label="显示 LinuxDo 登录按钮" valuePropName="checked">
                <Switch size="small" />
              </Form.Item>
              <Form.Item name="allow_new_accounts" label="允许新用户接入" valuePropName="checked">
                <Switch size="small" />
              </Form.Item>
              <Form.Item name="client_id" label="Client ID">
                <Input placeholder="填入 LinuxDo OAuth Client ID" />
              </Form.Item>
              <Form.Item name="client_secret" label="Client Secret">
                <Input.Password
                  prefix={<LockOutlined />}
                  placeholder={config?.client_secret_configured ? '已配置，留空表示不修改' : '填入 LinuxDo OAuth Client Secret'}
                />
              </Form.Item>
            </div>

            <div className="linuxdo-access-inline">
              <Form.Item name="clear_client_secret" valuePropName="checked" className="linuxdo-access-inline-switch">
                <Switch size="small" />
              </Form.Item>
              <span className="linuxdo-access-inline-copy">清空已保存的 Client Secret</span>
            </div>

            <div className="linuxdo-access-note">
              <span>当前状态：</span>
              <strong>{config?.status_summary || '未加载'}</strong>
            </div>

            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={configSaving}>
              保存入口配置
            </Button>
          </Form>
        </section>

        <section className="linuxdo-access-section">
          <div ref={batchEditorRef} />
          <div className="linuxdo-access-section-head">
            <Text strong>{editingBatch ? '编辑接入批次' : '新建接入批次'}</Text>
            <span className="linuxdo-access-section-copy">
              同时只启用一个批次。当前批次名额满后，系统会自动退回“仅已绑定可登录”。
            </span>
          </div>

          {editingBatch ? (
            <div className="linuxdo-access-editing-banner">
              <div className="linuxdo-access-editing-copy">
                <strong>正在编辑：</strong>
                <span>{editingBatch.batch_name}</span>
                <small>{editingBatch.batch_code}</small>
              </div>
              <Button icon={<PlusOutlined />} onClick={handleResetBatch}>
                取消编辑
              </Button>
            </div>
          ) : null}

          <Form<BatchFormValues>
            form={batchForm}
            layout="vertical"
            onFinish={(values) => void handleSaveBatch(values)}
            initialValues={buildBatchFormValues()}
          >
            <div className="linuxdo-access-form-grid linuxdo-access-form-grid--batch">
              <Form.Item name="batch_name" label="批次名称" rules={[{ required: true, message: '请输入批次名称' }]}>
                <Input placeholder="例如：第一批开放 50 人" />
              </Form.Item>
              <Form.Item name="max_accounts" label="接入名额" rules={[{ required: true, message: '请输入接入名额' }]}>
                <InputNumber min={1} max={100000} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="default_role" label="默认权限">
                <Select
                  options={[
                    { value: 'user', label: '普通用户' },
                    { value: 'admin', label: '管理员' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="is_enabled" label="启用该批次" valuePropName="checked">
                <Switch size="small" />
              </Form.Item>
              <Form.Item name="validity_mode" label="账号有效期模式">
                <Select
                  options={[
                    { value: 'duration', label: '按时长' },
                    { value: 'permanent', label: '永久' },
                    { value: 'fixed_at', label: '固定到期时间' },
                  ]}
                />
              </Form.Item>
              <Form.Item noStyle shouldUpdate={(prev, next) => prev.validity_mode !== next.validity_mode}>
                {({ getFieldValue }) =>
                  getFieldValue('validity_mode') === 'duration' ? (
                    <>
                      <Form.Item name="validity_unit" label="时长单位">
                        <Select
                          options={[
                            { value: 'day', label: '天' },
                            { value: 'month', label: '月' },
                            { value: 'year', label: '年' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="validity_value" label="时长数值">
                        <InputNumber min={1} max={3650} style={{ width: '100%' }} />
                      </Form.Item>
                    </>
                  ) : getFieldValue('validity_mode') === 'fixed_at' ? (
                    <Form.Item name="fixed_expires_at" label="固定到期时间">
                      <DatePicker showTime style={{ width: '100%' }} />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
              <Form.Item name="starts_at" label="开放开始时间">
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="ends_at" label="开放结束时间">
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
            </div>

            <Form.Item name="notes" label="备注">
              <Input.TextArea rows={3} placeholder="可选，用来记录这批开放的说明" />
            </Form.Item>

            <Space wrap>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={batchSaving}>
                {editingBatch ? '保存批次' : '创建批次'}
              </Button>
              <Button icon={<PlusOutlined />} onClick={handleResetBatch}>
                新建空白批次
              </Button>
            </Space>
          </Form>
        </section>
      </div>

      <section className="linuxdo-access-section linuxdo-access-section--full">
        <div className="linuxdo-access-section-head">
          <Text strong>批次记录</Text>
          <span className="linuxdo-access-section-copy">
            可以随时切换到旧批次继续编辑。若把某个旧批次重新启用，它会自动替代当前启用中的批次。
          </span>
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={config?.recent_batches || []}
          pagination={false}
          tableLayout="auto"
          scroll={{ x: 'max-content' }}
          rowClassName={(record) => (editingBatch?.id === record.id ? 'linuxdo-access-row-active' : '')}
        />
      </section>
    </Card>
  )
}

export default LinuxDoAccessPanel
