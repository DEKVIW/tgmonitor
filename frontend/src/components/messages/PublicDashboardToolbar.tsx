import MessageFilters from './MessageFilters'
import {
  PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES,
  PUBLIC_DASHBOARD_FALLBACK_TIME_RANGE,
} from '@/utils/publicDashboard'

const PublicDashboardToolbar = () => (
  <MessageFilters
    layoutVariant="guest-header"
    allowedTimeRanges={PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES}
    fallbackTimeRange={PUBLIC_DASHBOARD_FALLBACK_TIME_RANGE}
  />
)

export default PublicDashboardToolbar
