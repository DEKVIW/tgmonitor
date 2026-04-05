/**
 * 全局回到顶部按钮
 */

import { FloatButton } from 'antd'
import { VerticalAlignTopOutlined } from '@ant-design/icons'
import './BackToTopButton.css'

const BackToTopButton = () => {
  return (
    <FloatButton.BackTop
      visibilityHeight={280}
      className="back-to-top-button"
      icon={<VerticalAlignTopOutlined />}
      tooltip="回到顶部"
    />
  )
}

export default BackToTopButton
