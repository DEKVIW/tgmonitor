import apiClient from '@/utils/api'
import type {
  BackupRemoteFile,
  BackupRemoteFileDeleteResult,
  BackupRun,
  BackupTarget,
  BackupTargetPayload,
  BackupTargetTestResult,
} from '@/types/backup'

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

export const getBackupTargetRemoteFiles = async (targetId: number): Promise<BackupRemoteFile[]> => {
  const response = await apiClient.get<BackupRemoteFile[]>(`/admin/backups/targets/${targetId}/remote-files`)
  return response.data
}

export const deleteBackupTargetRemoteFile = async (
  targetId: number,
  remotePath: string,
): Promise<BackupRemoteFileDeleteResult> => {
  const response = await apiClient.delete<BackupRemoteFileDeleteResult>(`/admin/backups/targets/${targetId}/remote-files`, {
    params: {
      remote_path: remotePath,
    },
  })
  return response.data
}
