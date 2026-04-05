/**
 * 活跃热力图组件（按天/小时）
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { ActivityHeatmapResponse } from '@/types/statistics'

interface ActivityHeatmapProps {
  data: ActivityHeatmapResponse
}

const WEEKDAY_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const ActivityHeatmap = ({ data }: ActivityHeatmapProps) => {
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768

  const option = useMemo(() => {
    const dateIndexMap = new Map(data.dates.map((date, index) => [date, index]))
    const xAxisDates = data.dates.map((date) => {
      const current = dayjs(date)
      return isMobile
        ? current.format('MM/DD')
        : `${current.format('MM-DD')}\n${WEEKDAY_LABELS[current.day()]}`
    })
    const yAxisHours = data.hours.map((hour) => `${String(hour).padStart(2, '0')}:00`)
    const chartData = data.cells.map((cell) => [
      dateIndexMap.get(cell.date) ?? 0,
      cell.hour,
      cell.message_count,
    ])

    const totalMessages = data.cells.reduce((sum, cell) => sum + cell.message_count, 0)
    const peakCell = data.cells.reduce(
      (best, cell) => (cell.message_count > best.message_count ? cell : best),
      { date: data.dates[0] ?? dayjs().format('YYYY-MM-DD'), hour: 0, message_count: 0 }
    )

    const titleText = `最近${data.dates.length}天活跃热力图`
    const subtitleText =
      totalMessages > 0
        ? `峰值 ${dayjs(peakCell.date).format('MM-DD')} ${String(peakCell.hour).padStart(2, '0')}:00 · ${peakCell.message_count} 条`
        : '最近时段暂无活跃消息'

    return {
      backgroundColor: 'transparent',
      title: {
        text: titleText,
        subtext: subtitleText,
        left: 'center',
        top: 4,
        textStyle: {
          fontSize: 16,
          fontWeight: 700,
          color: '#15314b',
        },
        subtextStyle: {
          fontSize: 11,
          color: '#7a8696',
          lineHeight: 18,
        },
      },
      tooltip: {
        position: 'top',
        backgroundColor: 'rgba(11, 28, 44, 0.92)',
        borderWidth: 0,
        textStyle: {
          color: '#f8fbff',
          fontSize: 12,
        },
        formatter: (params: any) => {
          const [dateIndex, hour, value] = params.value as [number, number, number]
          const currentDate = data.dates[dateIndex]
          return [
            `${dayjs(currentDate).format('MM-DD')} ${WEEKDAY_LABELS[dayjs(currentDate).day()]}`,
            `${String(hour).padStart(2, '0')}:00 - ${String(hour).padStart(2, '0')}:59`,
            `消息数：${value}`,
          ].join('<br/>')
        },
      },
      grid: {
        top: isMobile ? '24%' : '22%',
        left: isMobile ? '15%' : '12%',
        right: isMobile ? '6%' : '5%',
        bottom: isMobile ? '12%' : '10%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: xAxisDates,
        splitArea: {
          show: true,
          areaStyle: {
            color: ['rgba(242, 247, 252, 0.74)', 'rgba(233, 241, 249, 0.9)'],
          },
        },
        axisLine: {
          lineStyle: {
            color: '#d6e2ee',
          },
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          interval: 0,
          color: '#4f6276',
          fontSize: isMobile ? 10 : 11,
          lineHeight: isMobile ? 14 : 16,
        },
      },
      yAxis: {
        type: 'category',
        data: yAxisHours,
        inverse: true,
        splitArea: {
          show: true,
          areaStyle: {
            color: ['rgba(255, 255, 255, 0.82)', 'rgba(247, 250, 253, 0.96)'],
          },
        },
        axisLine: {
          lineStyle: {
            color: '#d6e2ee',
          },
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          color: '#4f6276',
          fontSize: isMobile ? 10 : 11,
          formatter: (value: string) => (isMobile ? value.slice(0, 2) : value),
        },
      },
      visualMap: {
        show: false,
        min: 0,
        max: Math.max(data.max_count, 1),
        calculable: false,
        inRange: {
          color: ['#eef6ff', '#9ed0ff', '#5d96e8', '#2d4ea1', '#ffb45f', '#eb5a3c'],
        },
      },
      series: [
        {
          name: '活跃度',
          type: 'heatmap',
          data: chartData,
          progressive: 0,
          itemStyle: {
            borderRadius: 8,
            borderColor: 'rgba(255, 255, 255, 0.35)',
            borderWidth: 1,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 18,
              shadowColor: 'rgba(33, 87, 160, 0.28)',
              borderColor: '#ffffff',
              borderWidth: 1.5,
            },
          },
        },
      ],
    }
  }, [data, isMobile])

  if (data.cells.length === 0) {
    return (
      <div className="activity-heatmap-empty">
        <p>暂无活跃热力图数据</p>
      </div>
    )
  }

  return (
    <div className="activity-heatmap">
      <ReactECharts
        option={option}
        style={{ height: isMobile ? '300px' : '318px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
      <div className="activity-heatmap-legend" aria-hidden="true">
        <span className="activity-heatmap-legend__label">低活跃</span>
        <span className="activity-heatmap-legend__bar" />
        <span className="activity-heatmap-legend__label">高活跃</span>
      </div>
    </div>
  )
}

export default ActivityHeatmap
