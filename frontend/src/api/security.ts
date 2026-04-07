import apiClient from '@/utils/api'
import {
  DomainChallengeSyncResponse,
  PublicSecurityConfigResponse,
  SecurityChallengeVerifyRequest,
  SecurityChallengeVerifyResponse,
  SecurityConfigResponse,
  SecurityConfigUpdate,
} from '@/types/security'

export const getPublicSecurityConfig = async (): Promise<PublicSecurityConfigResponse> => {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/security/public`)
  return response.json() as Promise<PublicSecurityConfigResponse>
}

export const verifySearchTurnstile = async (
  data: SecurityChallengeVerifyRequest
): Promise<SecurityChallengeVerifyResponse> => {
  const response = await apiClient.post<SecurityChallengeVerifyResponse>('/security/turnstile/verify', data)
  return response.data
}

export const getSecurityConfig = async (): Promise<SecurityConfigResponse> => {
  const response = await apiClient.get<SecurityConfigResponse>('/admin/security')
  return response.data
}

export const updateSecurityConfig = async (data: SecurityConfigUpdate): Promise<SecurityConfigResponse> => {
  const response = await apiClient.put<SecurityConfigResponse>('/admin/security', data)
  return response.data
}

export const syncDomainAccessChallenge = async (): Promise<DomainChallengeSyncResponse> => {
  const response = await apiClient.post<DomainChallengeSyncResponse>('/admin/security/domain-access/sync')
  return response.data
}
