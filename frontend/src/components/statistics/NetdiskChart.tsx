/**
 * 网盘分布图表组件（饼图）
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { NetdiskDistributionResponse } from '@/types/statistics'
import { NETDISK_COLORS } from '@/utils/constants'

interface NetdiskChartProps {
  data: NetdiskDistributionResponse
}

const NetdiskChart = ({ data }: NetdiskChartProps) => {
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768

  const option = useMemo(() => {
    const chartData = data.distribution.map((item) => ({
      value: item.link_count,
      name: `${item.netdisk_name} ${(item.percentage * 100).toFixed(1)}%`,
      percentage: item.percentage,
    }))

    const colors = chartData.map(
      (item) => NETDISK_COLORS[item.name.split(' ')[0]] || '#cccccc'
    )

    return {
      title: {
        text: '最近24小时网盘链接分布',
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 600,
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          return `${params.name}<br/>链接数量: ${params.value}<br/>占比: ${(params.data.percentage * 100).toFixed(1)}%`
        },
      },
      legend: isMobile
        ? {
            type: 'scroll',
            orient: 'horizontal',
            bottom: 0,
            left: 'center',
            textStyle: { fontSize: 12 },
          }
        : {
            type: 'scroll',
            orient: 'vertical',
            right: 10,
            top: 'middle',
            textStyle: { fontSize: 12 },
          },
      series: [
        {
          name: '网盘类型',
          type: 'pie',
          radius: isMobile ? ['30%', '60%'] : ['40%', '70%'],
          center: isMobile ? ['50%', '50%'] : ['40%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 2,
          },
          label: {
            show: true,
            position: 'outside',
            formatter: (params: any) => {
              return `${params.name}\n${params.value}`
            },
            fontSize: isMobile ? 10 : 12,
          },
          labelLine: {
            show: true,
            length: isMobile ? 15 : 20,
            length2: isMobile ? 10 : 15,
            lineStyle: {
              width: 1,
            },
          },
          emphasis: {
            label: {
              show: true,
              fontSize: isMobile ? 12 : 14,
              fontWeight: 'bold',
            },
            labelLine: {
              show: true,
              length: isMobile ? 20 : 25,
              length2: isMobile ? 15 : 20,
            },
          },
          data: chartData,
          color: colors,
        },
      ],
    }
  }, [data])

  if (data.distribution.length === 0) {
    return (
      <div className="netdisk-chart-empty">
        <p>暂无网盘链接数据</p>
      </div>
    )
  }

  return (
    <div className="netdisk-chart">
      <ReactECharts
        option={option}
        style={{ height: '350px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}

export default NetdiskChart

