import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

const appTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#0b6bcb',
    colorInfo: '#0b6bcb',
    colorSuccess: '#15803d',
    colorWarning: '#b7791f',
    colorError: '#c2410c',
    colorText: '#16324a',
    colorTextSecondary: '#5d7288',
    colorBorder: '#d8e3ee',
    colorBgLayout: '#eef4f8',
    colorBgContainer: 'rgba(255, 255, 255, 0.88)',
    colorBgElevated: '#ffffff',
    borderRadius: 14,
    borderRadiusLG: 24,
    controlHeight: 40,
    fontFamily:
      '"Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: {
      headerBg: 'transparent',
      siderBg: 'transparent',
      bodyBg: 'transparent',
    },
    Button: {
      borderRadius: 14,
      controlHeight: 40,
      fontWeight: 600,
      primaryShadow: '0 12px 24px rgba(11, 107, 203, 0.22)',
      defaultShadow: 'none',
    },
    Card: {
      borderRadiusLG: 24,
    },
    Input: {
      controlHeight: 42,
    },
    InputNumber: {
      controlHeight: 42,
    },
    Select: {
      controlHeight: 42,
    },
    Table: {
      headerBg: '#f4f8fb',
      headerColor: '#294359',
      rowHoverBg: '#f7fbff',
      borderColor: '#d8e3ee',
      headerSplitColor: '#d8e3ee',
    },
    Tabs: {
      itemColor: '#5d7288',
      itemHoverColor: '#0b6bcb',
      itemSelectedColor: '#0b6bcb',
      inkBarColor: '#0b6bcb',
    },
  },
} as const

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ConfigProvider locale={zhCN} theme={appTheme}>
    <App />
  </ConfigProvider>,
)

