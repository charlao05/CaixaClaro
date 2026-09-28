import { api, type Paginado } from './api'

export type ItemFila = {
  id: string
  data: string
  descricao_bruta: string
  valor: string
  origem: string
  categoria: string | null
  categoria_original: string | null
  proposito: string | null
  patrimonio: string | null
  tratamento_tributario: string | null
  confianca: number | null
  needs_review: boolean
  via: string | null
  motivo: string | null
  criado_em: string
  atualizado_em: string
  versao: number
}

export type ListarFilaOpts = {
  limite?: number
  cursor?: string
}

export function listarFila(
  token: string,
  opts: ListarFilaOpts = {},
): Promise<Paginado<ItemFila>> {
  const params = new URLSearchParams()
  if (opts.limite !== undefined) params.set('limite', String(opts.limite))
  if (opts.cursor) params.set('cursor', opts.cursor)
  const qs = params.toString()
  const path = qs ? `/transacoes/fila?${qs}` : '/transacoes/fila'
  return api<Paginado<ItemFila>>(path, { token })
}