interface ChannelTrendSparklineProps {
  values: number[]
  width?: number
  height?: number
}

const ChannelTrendSparkline = ({
  values,
  width = 132,
  height = 40,
}: ChannelTrendSparklineProps) => {
  const points = values.length > 0 ? values : [0]
  const maxValue = Math.max(...points, 1)
  const paddingX = 4
  const paddingY = 5
  const plotWidth = Math.max(width - paddingX * 2, 1)
  const plotHeight = Math.max(height - paddingY * 2, 1)
  const stepX = points.length > 1 ? plotWidth / (points.length - 1) : 0
  const baselineY = paddingY + plotHeight

  const coords = points.map((value, index) => {
    const x = paddingX + stepX * index
    const y = paddingY + plotHeight - (value / maxValue) * plotHeight
    return { x, y, value }
  })

  const linePath = coords
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ')
  const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(2)} ${baselineY.toFixed(2)} L ${coords[0].x.toFixed(2)} ${baselineY.toFixed(2)} Z`
  const lastPoint = coords[coords.length - 1]

  return (
    <div className="channel-trend-sparkline" title={points.join(' / ')}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="channel message trend">
        <path className="channel-trend-sparkline__area" d={areaPath} />
        <path className="channel-trend-sparkline__line" d={linePath} />
        <circle
          className="channel-trend-sparkline__dot"
          cx={lastPoint.x.toFixed(2)}
          cy={lastPoint.y.toFixed(2)}
          r="2.8"
        />
      </svg>
    </div>
  )
}

export default ChannelTrendSparkline
