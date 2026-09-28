import { api } from './api'

export type Conta = {
  id: string
  provider: string
  provider_account_id: string
  nome: string
  criado_em: string
}

export type ConnectTokenResponse = {
  connect_token: string
  expira_em: string | null
}

export type RevogarContaResponse = {
  item_id: string
  ja_revogado: boolean
}

export type ListarContasResponse = {
  itens: Conta[]
}

export function conectarBanco(token: string): Promise<ConnectTokenResponse> {
  return api<ConnectTokenResponse>('/contas/conectar', {
    method: 'POST',
    token,
  })
}

export function listarContas(token: string): Promise<ListarContasResponse> {
  return api<ListarContasResponse>('/contas', { token })
}

export function revogarConta(
  token: string,
  contaId: string,
): Promise<RevogarContaResponse> {
  return api<RevogarContaResponse>(`/contas/${contaId}/revogar`, {
    method: 'POST',
    token,
  })
}