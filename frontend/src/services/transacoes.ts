import { api, type Paginado } from './api'
import type { OpcaoResposta } from './fila'

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
  proposito: string | null
  // Nome em linguagem simples, decidido pelo backend.
  rotulo: string
  confirmada: boolean
  needs_review: boolean
  criado_em: string
  atualizado_em: string
  versao: number
}

export type ColarResponse = {
  paste_id: string
  importados: number
  // Quantos dos importados repetem lançamentos que já existiam (mesma data,
  // valor e descrição). É aviso: a pessoa decide se apaga.
  possiveis_repetidos?: number
  itens: TransacaoResumo[]
}

export type ImportarResponse = {
  import_id: string
  importados: number
  possiveis_repetidos?: number
  itens: TransacaoResumo[]
}

export type ApagadosResponse = {
  apagados: number
  ids: string[]
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

export type OpcoesResposta = {
  entrada: OpcaoResposta[]
  saida: OpcaoResposta[]
}

export function getOpcoesResposta(token: string): Promise<OpcoesResposta> {
  return api<OpcoesResposta>('/transacoes/opcoes-resposta', { token })
}

export type AnotarEntrada = {
  data: string
  descricao: string
  // string decimal com sinal: positivo = entrou, negativo = saiu
  valor: string
  categoria?: string
  proposito?: string
}

// Anota um lancamento sem extrato (quem recebe em dinheiro tambem comeca).
export function anotar(
  token: string,
  entrada: AnotarEntrada,
  idempotencyKey?: string,
): Promise<TransacaoCompleta> {
  return api<TransacaoCompleta>('/transacoes/manual', {
    method: 'POST',
    body: entrada,
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

export function apagarTransacao(token: string, id: string): Promise<ApagadosResponse> {
  return api<ApagadosResponse>(`/transacoes/${id}`, { method: 'DELETE', token })
}

// Lote = uma colagem (paste_id) ou um arquivo importado (import_id).
export function desfazerLote(token: string, loteId: string): Promise<ApagadosResponse> {
  return api<ApagadosResponse>(`/transacoes/lotes/${encodeURIComponent(loteId)}`, {
    method: 'DELETE',
    token,
  })
}

export function apagarRepetidos(token: string, loteId: string): Promise<ApagadosResponse> {
  return api<ApagadosResponse>(
    `/transacoes/lotes/${encodeURIComponent(loteId)}/repetidos`,
    { method: 'DELETE', token },
  )
}
