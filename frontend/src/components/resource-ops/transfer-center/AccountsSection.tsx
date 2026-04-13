import { Alert, Button, Card, Empty, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CheckCircleOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'

import type { PanTransferAccountItem } from '@/types/panTransfer'

import { formatDateTime } from './shared'

const { Title, Paragraph } = Typography

type AccountsSectionProps = {
  accounts: PanTransferAccountItem[]
  accountsLoading: boolean
  validatingAccountId: number | null
  deletingAccountId: number | null
  missingPlatforms: Array<{ label: string; value: string }>
  onRefresh: () => void
  onCreate: () => void
  onEdit: (account: PanTransferAccountItem) => void
  onValidate: (account: PanTransferAccountItem) => void
  onDelete: (account: PanTransferAccountItem) => void
}

const AccountsSection = ({
  accounts,
  accountsLoading,
  validatingAccountId,
  deletingAccountId,
  missingPlatforms,
  onRefresh,
  onCreate,
  onEdit,
  onValidate,
  onDelete,
}: AccountsSectionProps) => {
  const columns: ColumnsType<PanTransferAccountItem> = [
    {
      title: '平台 / 账号',
      dataIndex: 'account_name',
      key: 'account_name',
      width: 180,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell resource-ops-transfer-account-cell">
          <span className="resource-ops-transfer-title-main resource-ops-transfer-account-main" title={record.account_name}>
            {record.account_name}
          </span>
          <span className="resource-ops-transfer-title-sub resource-ops-transfer-account-sub" title={record.platform}>
            {record.platform}
          </span>
        </div>
      ),
    },
    {
      title: '默认策略',
      key: 'strategy',
      width: 210,
      render: (_, record) => (
        <div className="resource-ops-transfer-tag-stack resource-ops-transfer-account-tags">
          <Tag color={record.default_share_mode === 'public' ? 'blue' : 'default'}>
            {record.default_share_mode === 'public' ? '转存后分享' : '仅转存'}
          </Tag>
          {record.default_save_root ? <Tag>{record.default_save_root}</Tag> : null}
          {record.is_default ? <Tag color="gold">默认账号</Tag> : null}
        </div>
      ),
    },
    {
      title: '凭据与校验',
      key: 'validation',
      width: 248,
      render: (_, record) => {
        const validated = Boolean(record.last_validated_at)
        const ok = validated && !record.last_error_message
        return (
          <div className="resource-ops-transfer-validation resource-ops-transfer-account-validation">
            <Space wrap size={[6, 6]}>
              <Tag color={record.is_enabled ? 'success' : 'default'}>{record.is_enabled ? '启用' : '停用'}</Tag>
              <Tag color={record.credential_configured ? 'processing' : 'warning'}>
                {record.credential_configured ? 'Cookie 已配置' : '缺少 Cookie'}
              </Tag>
              <Tag color={validated ? (ok ? 'success' : 'error') : 'default'}>
                {validated ? (ok ? '最近校验通过' : '最近校验失败') : '未校验'}
              </Tag>
            </Space>
            <small>{record.last_validated_at ? `校验时间 ${formatDateTime(record.last_validated_at)}` : '建议首次配置后立即校验'}</small>
            {record.last_error_message ? <small className="is-error">{record.last_error_message}</small> : null}
          </div>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 176,
      render: (_, record) => (
        <Space wrap size={[6, 6]} className="resource-ops-transfer-account-actions">
          <Button
            size="small"
            icon={<CheckCircleOutlined />}
            loading={validatingAccountId === record.id}
            onClick={() => onValidate(record)}
          >
            校验
          </Button>
          <Button size="small" onClick={() => onEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除这个账号吗？"
            description="如果历史批次仍引用这个账号，需要先删除对应批次。"
            onConfirm={() => onDelete(record)}
          >
            <Button size="small" danger loading={deletingAccountId === record.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card className="resource-ops-panel-card">
      <div className="resource-ops-transfer-card-head">
        <div>
          <Title level={4}>网盘账号</Title>
          <Paragraph className="resource-ops-transfer-copy">
            配置用于转存的目标账号、默认保存目录和默认分享策略。账号支持单独校验 Cookie 连通性，失败原因会直接展示在这里。
          </Paragraph>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} loading={accountsLoading} onClick={onRefresh}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreate}>
            新增账号
          </Button>
        </Space>
      </div>

      <div className="resource-ops-transfer-summary">
        <div className="resource-ops-transfer-summary-item">
          <span>账号总数</span>
          <strong>{accounts.length}</strong>
          <small>当前支持百度网盘与夸克网盘</small>
        </div>
        <div className="resource-ops-transfer-summary-item">
          <span>启用账号</span>
          <strong>{accounts.filter((item) => item.is_enabled).length}</strong>
          <small>只有启用账号才会进入推荐和执行</small>
        </div>
        <div className="resource-ops-transfer-summary-item">
          <span>最近校验通过</span>
          <strong>{accounts.filter((item) => item.last_validated_at && !item.last_error_message).length}</strong>
          <small>建议创建或更新 Cookie 后立即校验一次</small>
        </div>
      </div>

      {missingPlatforms.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          message="仍有平台没有可用账号"
          description={`缺少：${missingPlatforms.map((item) => item.label).join('、')}。预览仍可用，但这些平台暂时不能创建真实转存批次。`}
        />
      ) : null}

      <Table
        style={{ marginTop: 16 }}
        rowKey="id"
        loading={accountsLoading}
        dataSource={accounts}
        columns={columns}
        pagination={false}
        scroll={{ x: 920 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无转存账号" /> }}
      />
    </Card>
  )
}

export default AccountsSection
