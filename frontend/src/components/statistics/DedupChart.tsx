/**
 * 去重统计图表组件（柱状图）
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { DedupStatsResponse } from '@/types/statistics'
import dayjs from 'dayjs'

interface DedupChartProps {
  data: DedupStatsResponse
}

const DedupChart = ({ data }: DedupChartProps) => {
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768

  const option = useMemo(() => {
    const hours = data.hours.map((h) => dayjs(h.hour).format('HH:mm'))
    const deletedCounts = data.hours.map((h) => h.deleted_count)

    return {
      title: {
        text: '最近10小时每小时去重删除数',
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 600,
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
        formatter: (params: any) => {
          const param = params[0]
          return `${param.name}<br/>${param.seriesName}: ${param.value}`
        },
      },
      grid: {
        left: isMobile ? '10%' : '7%',
        right: isMobile ? '6%' : '4%',
        bottom: isMobile ? '12%' : '8%',
        top: '12%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: hours,
        axisLabel: {
          fontSize: 12,
        },
      },
      yAxis: {
        type: 'value',
        show: true,
        axisLabel: {
          show: true,
          color: '#555',
          fontSize: 12,
          formatter: (value: number) => value.toString(),
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#eee' },
        },
      },
      series: [
        {
          name: '删除数量',
          type: 'bar',
          data: deletedCounts,
          itemStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: '#667eea' },
                { offset: 1, color: '#764ba2' },
              ],
            },
          },
          label: {
            show: true,
            position: 'top',
            fontSize: 12,
            fontWeight: 'bold',
          },
        },
      ],
    }
  }, [data])

  return (
    <div className="dedup-chart">
      <ReactECharts
        option={option}
        style={{ height: isMobile ? '320px' : '360px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}

export default DedupChart

