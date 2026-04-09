import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

import type { ResourceOpsPlatformDistributionItem } from '@/types/resourceOps'

interface ResourceOpsPlatformChartProps {
  items: ResourceOpsPlatformDistributionItem[]
  height?: number
}

const ResourceOpsPlatformChart = ({ items, height = 320 }: ResourceOpsPlatformChartProps) => {
  const option = useMemo(() => {
    const colors = ['#0b6bcb', '#1b9aaa', '#e08e12', '#da5f3f', '#5b7c8d', '#7a9e2a', '#8752a3', '#d1495b']
    return {
      tooltip: {
        trigger: 'item',
        formatter: '{b}<br/>{c} 点击 ({d}%)',
      },
      legend: {
        bottom: 0,
        left: 'center',
      },
      color: colors,
      series: [
        {
          type: 'pie',
          radius: ['42%', '70%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          itemStyle: {
            borderRadius: 12,
            borderColor: '#fff',
            borderWidth: 3,
          },
          label: {
            formatter: '{b}\n{d}%',
          },
          data: items.map((item) => ({
            name: item.platform,
            value: item.click_count,
          })),
        },
      ],
    }
  }, [items])

  return <ReactECharts option={option} style={{ height, width: '100%' }} opts={{ renderer: 'canvas' }} />
}

export default ResourceOpsPlatformChart
