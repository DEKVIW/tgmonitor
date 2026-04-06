import type { ComponentProps, ReactNode } from 'react'
import { Tooltip } from 'antd'
import './HintTooltip.css'

interface HintTooltipProps {
  content: ReactNode
  placement?: ComponentProps<typeof Tooltip>['placement']
}

const HintTooltip = ({ content, placement = 'top' }: HintTooltipProps) => (
  <Tooltip
    title={<div className="hint-tooltip-content">{content}</div>}
    placement={placement}
    trigger={['hover', 'focus']}
  >
    <span className="hint-tooltip-trigger" role="button" tabIndex={0} aria-label="查看说明">
      ?
    </span>
  </Tooltip>
)

export default HintTooltip
