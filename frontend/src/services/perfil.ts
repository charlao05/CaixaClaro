import { api } from './api'
import type { Regime } from './auth'

export type Perfil = {
  id: string
  email: string
  nome: string | null
  regime: Regime
  mes_abertura_mei: number | null
  ano_abertura_mei: number | null
  telegram_chat_id: string | null
  criado_em: string
  atualizado_em: string
}

export type PerfilAtualizar = {
  nome?: string | null
  regime?: Regime | null
  mes_abertura_mei?: number | null
  ano_abertura_mei?: number | null
}

export type PerfilAtualizadoResponse = {
  ok: true
  atualizados: string[]
}

export function getPerfil(token: string): Promise<Perfil> {
  return api<Perfil>('/perfil', { token })
}

export function atualizarPerfil(
  token: string,
  dados: PerfilAtualizar,
): Promise<PerfilAtualizadoResponse> {
  return api<PerfilAtualizadoResponse>('/perfil', {
    method: 'PATCH',
    body: dados,
    token,
  })
}