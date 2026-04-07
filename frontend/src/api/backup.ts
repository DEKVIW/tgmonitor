import apiClient from '@/utils/api'
import type { BackupRun, BackupRunDeleteResult, BackupTarget, BackupTargetPayload, BackupTargetTestResult } from '@/types/backup'

export const getBackupTargets = async (): Promise<BackupTarget[]> => {
  const response = await apiClient.get<BackupTarget[]>('/admin/backups/targets')
  return response.data
}

export const createBackupTarget = async (payload: BackupTargetPayload): Promise<BackupTarget> => {
  const response = await apiClient.post<BackupTarget>('/admin/backups/targets', payload)
  return response.data
}

export const updateBackupTarget = async (targetId: number, payload: BackupTargetPayload): Promise<BackupTarget> => {
  const response = await apiClient.put<BackupTarget>(`/admin/backups/targets/${targetId}`, payload)
  return response.data
}

export const deleteBackupTarget = async (targetId: number): Promise<void> => {
  await apiClient.delete(`/admin/backups/targets/${targetId}`)
}

export const runBackupTarget = async (targetId: number): Promise<BackupRun> => {
  const response = await apiClient.post<BackupRun>(`/admin/backups/targets/${targetId}/run`)
  return response.data
}

export const testBackupTarget = async (targetId: number): Promise<BackupTargetTestResult> => {
  const response = await apiClient.post<BackupTargetTestResult>(`/admin/backups/targets/${targetId}/test`)
  return response.data
}

export const getBackupRuns = async (params: { limit?: number; target_id?: number } = {}): Promise<BackupRun[]> => {
  const search = new URLSearchParams()
  if (params.limit !== undefined) {
    search.set('limit', String(params.limit))
  }
  if (params.target_id !== undefined) {
    search.set('target_id', String(params.target_id))
  }
  const query = search.toString()
  const response = await apiClient.get<BackupRun[]>(`/admin/backups/runs${query ? `?${query}` : ''}`)
  return response.data
}

export const deleteBackupRuns = async (ids: number[]): Promise<BackupRunDeleteResult> => {
  const response = await apiClient.post<BackupRunDeleteResult>('/admin/backups/runs/delete', { ids })
  return response.data
}
