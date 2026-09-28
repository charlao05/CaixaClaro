import { api } from './api'

export type TokenVinculacaoResponse = {
  token: string
  expira_em: string
}

export function gerarTokenVinculacao(
  token: string,
): Promise<TokenVinculacaoResponse> {
  return api<TokenVinculacaoResponse>('/telegram/token-vinculacao', {
    method: 'POST',
    token,
  })
}