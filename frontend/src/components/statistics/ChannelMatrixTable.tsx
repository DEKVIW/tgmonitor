import { ReloadOutlined } from '@ant-design/icons'
import { Button, Empty, Segmented, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { AdminChannelMatrixResponse, AdminChannelMatrixRow } from '@/types/statistics'

import ChannelTrendSparkline from './ChannelTrendSparkline'

interface ChannelMatrixTableProps {
  data: AdminChannelMatrixResponse | null
  loading?: boolean
  days: number
  onDaysChange: (value: number) => void
  onReload: () => void
}

const DAY_OPTIONS = [
  { label: '\u8fd17\u5929', value: 7 },
  { label: '\u8fd114\u5929', value: 14 },
  { label: '\u8fd130\u5929', value: 30 },
]

const weekdayFormatter = new Intl.DateTimeFormat('zh-CN', { weekday: 'short' })

const formatShortDate = (value: string) => `${value.slice(5, 7)}-${value.slice(8, 10)}`

const formatWeekday = (value: string) => weekdayFormatter.format(new Date(`${value}T12:00:00`))

const formatNumber = (value: number) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))

const buildHeatCellStyle = (messageCount: number, maxDailyMessages: number) => {
  if (messageCount <= 0 || maxDailyMessages <= 0) {
    return {
      background: '#f7fbff',
      borderColor: 'rgba(216, 227, 238, 0.95)',
      color: '#5d7288',
    }
  }

  const intensity = Math.min(messageCount / maxDailyMessages, 1)
  const alpha = 0.16 + intensity * 0.5

  return {
    background: `linear-gradient(180deg, rgba(11, 107, 203, ${alpha}) 0%, rgba(11, 107, 203, ${Math.max(alpha - 0.08, 0.14)}) 100%)`,
    borderColor: `rgba(11, 107, 203, ${Math.min(alpha + 0.08, 0.75)})`,
    color: intensity >= 0.55 ? '#ffffff' : '#16324a',
  }
}

const ChannelMatrixTable = ({
  data,
  loading = false,
  days,
  onDaysChange,
  onReload,
}: ChannelMatrixTableProps) => {
  const dates = data?.dates || []
  const rows = data?.rows || []
  const maxDailyMessages = data?.max_daily_messages || 0

  const columns: ColumnsType<AdminChannelMatrixRow> = [
    {
      title: '\u9891\u9053',
      dataIndex: 'monitor_channel_title',
      key: 'monitor_channel_title',
      fixed: 'left',
      width: 260,
      sorter: (left, right) =>
        (left.monitor_channel_title || left.monitor_channel_key || '').localeCompare(
          right.monitor_channel_title || right.monitor_channel_key || '',
          'zh-CN'
        ),
      render: (_, row) => (
        <div className="channel-matrix-channel">
          <strong>{row.monitor_channel_title || row.monitor_channel_key || '\u672a\u547d\u540d\u9891\u9053'}</strong>
          <small>{row.monitor_channel_key || `config:${row.monitor_channel_config_id || 'unknown'}`}</small>
        </div>
      ),
    },
    {
      title: '\u6d88\u606f\u6570',
      dataIndex: 'total_messages',
      key: 'total_messages',
      fixed: 'left',
      width: 112,
      defaultSortOrder: 'descend',
      sorter: (left, right) => (left.total_messages || 0) - (right.total_messages || 0),
      render: (value: number) => <span className="channel-matrix-metric">{formatNumber(value || 0)}</span>,
    },
    {
      title: '\u94fe\u63a5\u6570',
      dataIndex: 'total_links',
      key: 'total_links',
      fixed: 'left',
      width: 112,
      sorter: (left, right) => (left.total_links || 0) - (right.total_links || 0),
      render: (value: number) => <span className="channel-matrix-metric">{formatNumber(value || 0)}</span>,
    },
    {
      title: '\u8d8b\u52bf',
      key: 'trend',
      fixed: 'left',
      width: 160,
      sorter: (left, right) => {
        const leftPeak = Math.max(...(left.trend || [0]))
        const rightPeak = Math.max(...(right.trend || [0]))
        return leftPeak - rightPeak
      },
      render: (_, row) => <ChannelTrendSparkline values={row.trend || []} />,
    },
    ...dates.map((date) => ({
      title: (
        <div className="channel-matrix-date-head">
          <strong>{formatShortDate(date)}</strong>
          <span>{formatWeekday(date)}</span>
        </div>
      ),
      key: date,
      width: 110,
      sorter: (left: AdminChannelMatrixRow, right: AdminChannelMatrixRow) =>
        (left.message_counts?.[date] || 0) - (right.message_counts?.[date] || 0),
      render: (_: unknown, row: AdminChannelMatrixRow) => {
        const messageCount = row.message_counts?.[date] || 0
        const linkCount = row.link_counts?.[date] || 0
        return (
          <div className="channel-matrix-cell" style={buildHeatCellStyle(messageCount, maxDailyMessages)}>
            <span>{messageCount}</span>
            <small>{linkCount > 0 ? `L ${linkCount}` : '\u00A0'}</small>
          </div>
        )
      },
    })),
  ]

  return (
    <div className="channel-matrix-wrap">
      <div className="channel-matrix-toolbar">
        <div className="channel-matrix-toolbar__copy">
          <strong>{'\u9891\u9053\u6d88\u606f\u77e9\u9635'}</strong>
          <span>
            Rows are monitored channels. Columns are dates. Cell primary value is message count, and the
            secondary value is extracted link count.
            {data?.available_since ? ` Reliable source fields are available from ${data.available_since}.` : ''}
          </span>
        </div>
        <div className="channel-matrix-toolbar__actions">
          <Segmented options={DAY_OPTIONS} value={days} onChange={(value) => onDaysChange(Number(value))} />
          <Button icon={<ReloadOutlined />} onClick={onReload}>
            {'\u5237\u65b0'}
          </Button>
        </div>
      </div>

      {rows.length === 0 && !loading ? (
        <div className="channel-matrix-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No new messages with trusted monitored-channel source fields yet"
          />
        </div>
      ) : (
        <Table<AdminChannelMatrixRow>
          rowKey="row_key"
          loading={loading}
          dataSource={rows}
          columns={columns}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: (total) => `${total} channels`,
          }}
          scroll={{ x: 980 + dates.length * 110 }}
          sticky
          size="middle"
          className="channel-matrix-table"
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No channel matrix data" />,
          }}
        />
      )}
    </div>
  )
}

export default ChannelMatrixTable
