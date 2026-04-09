import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

import type { ResourceOpsTrendPoint } from '@/types/resourceOps'

interface ResourceOpsTrendChartProps {
  data: ResourceOpsTrendPoint[]
  height?: number
}

const ResourceOpsTrendChart = ({ data, height = 320 }: ResourceOpsTrendChartProps) => {
  const option = useMemo(() => {
    const dates = data.map((item) => item.date.slice(5))
    const clicks = data.map((item) => item.click_count)
    const sessions = data.map((item) => item.unique_sessions)

    return {
      tooltip: {
        trigger: 'axis',
      },
      legend: {
        top: 0,
        right: 0,
        data: ['点击量', '会话数'],
      },
      grid: {
        left: '4%',
        right: '4%',
        top: '14%',
        bottom: '6%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
      },
      yAxis: {
        type: 'value',
        splitLine: {
          lineStyle: {
            color: 'rgba(181, 197, 212, 0.26)',
          },
        },
      },
      series: [
        {
          name: '点击量',
          type: 'line',
          smooth: true,
          data: clicks,
          lineStyle: {
            width: 3,
            color: '#0b6bcb',
          },
          itemStyle: {
            color: '#0b6bcb',
          },
          areaStyle: {
            color: 'rgba(11, 107, 203, 0.14)',
          },
        },
        {
          name: '会话数',
          type: 'line',
          smooth: true,
          data: sessions,
          lineStyle: {
            width: 2,
            color: '#d47a12',
          },
          itemStyle: {
            color: '#d47a12',
          },
        },
      ],
    }
  }, [data])

  return <ReactECharts option={option} style={{ height, width: '100%' }} opts={{ renderer: 'canvas' }} />
}

export default ResourceOpsTrendChart
