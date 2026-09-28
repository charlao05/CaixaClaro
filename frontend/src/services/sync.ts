import { api } from './api'

export type SyncStatus =
  | 'pendente'
  | 'processando'
  | 'completed'
  | 'failed'

export type IniciarSyncResponse = {
  sync_id: string
  status: SyncStatus
}

export type SyncRequest = {
  sync_id: string
  status: SyncStatus
  erro: string | null
  criado_em: string
}

export function iniciarSync(
  token: string,
  contaId: string,
): Promise<IniciarSyncResponse> {
  return api<IniciarSyncResponse>(`/contas/${contaId}/sync`, {
    method: 'POST',
    token,
  })
}

export function consultarSync(
  token: string,
  syncId: string,
): Promise<SyncRequest> {
  return api<SyncRequest>(`/sync/${syncId}`, { token })
}