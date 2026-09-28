import { api, type Paginado } from './api'

export type TransacaoResumo = {
  id: string
  data: string
  descricao_bruta: string
  valor: string
  origem: string
  line_index: number
}

export type TransacaoCompleta = TransacaoResumo & {
  categoria: string | null
  needs_review: boolean
  criado_em: string
  atualizado_em: string
  versao: number
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

export type ListarTransacoesOpts = {
  desde?: string
  ate?: string
  limite?: number
  cursor?: string
}

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

export function listarTransacoes(
  token: string,
  opts: ListarTransacoesOpts = {},
): Promise<Paginado<TransacaoCompleta>> {
  const params = new URLSearchParams()
  if (opts.desde) params.set('desde', opts.desde)
  if (opts.ate) params.set('ate', opts.ate)
  if (opts.limite !== undefined) params.set('limite', String(opts.limite))
  if (opts.cursor) params.set('cursor', opts.cursor)
  const qs = params.toString()
  const path = qs ? `/transacoes?${qs}` : '/transacoes'
  return api<Paginado<TransacaoCompleta>>(path, { token })
}