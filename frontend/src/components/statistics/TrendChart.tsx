/**
 * 趋势图表组件（折线图）
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { DailyTrendResponse } from '@/types/statistics'

interface TrendChartProps {
  data: DailyTrendResponse
}

const TrendChart = ({ data }: TrendChartProps) => {
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768

  const option = useMemo(() => {
    const dates = data.days.map((d) => d.date)
    const messages = data.days.map((d) => d.messages)
    const links = data.days.map((d) => d.links)

    return {
      title: {
        text: '最近10天消息与链接趋势',
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 600,
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
        },
      },
      legend: {
        data: ['消息数', '链接数'],
        top: 10,
        right: 20,
        orient: 'horizontal',
        itemGap: 20,
      },
      grid: {
        left: isMobile ? '8%' : '6%',
        right: isMobile ? '6%' : '6%',
        bottom: isMobile ? '12%' : '8%',
        top: '12%',
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dates,
        axisLabel: {
          rotate: -45,
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
          formatter: (value: number) => {
            if (value >= 1000) {
              return `${(value / 1000).toFixed(1)}k`
            }
            return value.toString()
          },
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#eee' },
        },
      },
      series: [
        {
          name: '消息数',
          type: 'line',
          data: messages,
          smooth: true,
          lineStyle: {
            width: 3,
            color: '#409eff',
          },
          itemStyle: {
            color: '#409eff',
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
                { offset: 1, color: 'rgba(64, 158, 255, 0.1)' },
              ],
            },
          },
          label: {
            show: true,
            position: 'top',
            fontSize: 12,
            fontWeight: 'bold',
            color: '#409eff',
            formatter: (params: any) => {
              const value = params.value
              return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toString()
            },
          },
        },
        {
          name: '链接数',
          type: 'line',
          data: links,
          smooth: true,
          lineStyle: {
            width: 3,
            color: '#faad14',
          },
          itemStyle: {
            color: '#faad14',
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(250, 173, 20, 0.3)' },
                { offset: 1, color: 'rgba(250, 173, 20, 0.1)' },
              ],
            },
          },
          label: {
            show: true,
            position: 'top',
            fontSize: 12,
            fontWeight: 'bold',
            color: '#faad14',
            formatter: (params: any) => {
              const value = params.value
              return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toString()
            },
          },
        },
      ],
    }
  }, [data])

  return (
    <div className="trend-chart">
      <ReactECharts
        option={option}
        style={{ height: isMobile ? '320px' : '360px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}

export default TrendChart

