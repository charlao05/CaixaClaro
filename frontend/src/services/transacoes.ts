import { api } from './api'

export type TransacaoResumo = {
  id: string
  data: string
  descricao_bruta: string
  valor: string
  origem: string
  line_index: number
}

export type ColarResponse = {
  paste_id: string
  importados: number
  itens: TransacaoResumo[]
}

export type ImportarResponse = {
  import_id: string
  importados: number
  itens: TransacaoResumo[]
}

export type FormatoArquivo = 'csv' | 'ofx'

function novaChave(): string {
  return crypto.randomUUID()
}

export function colar(
  token: string,
  texto: string,
  idempotencyKey?: string,
): Promise<ColarResponse> {
  return api<ColarResponse>('/transacoes/extrato/colar', {
    method: 'POST',
    body: { texto },
    token,
    idempotencyKey: idempotencyKey ?? novaChave(),
  })
}

export function importar(
  token: string,
  formato: FormatoArquivo,
  conteudoBase64: string,
  idempotencyKey?: string,
): Promise<ImportarResponse> {
  return api<ImportarResponse>('/transacoes/importar', {
    method: 'POST',
    body: { formato, conteudo_base64: conteudoBase64 },
    token,
    idempotencyKey: idempotencyKey ?? novaChave(),
  })
}