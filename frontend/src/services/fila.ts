import { api, type Paginado } from './api'

// Opcao de resposta em linguagem simples. Vem do backend, ja coerente com a
// direcao do dinheiro (entrou / saiu).
export type OpcaoResposta = {
  id: string
  label: string
  descricao: string
  categoria: string
  proposito: string
}

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
  opcoes: OpcaoResposta[]
}

export type ListarFilaOpts = {
  limite?: number
  cursor?: string
}

export type ConfirmarResponse = {
  tx_id: string
  categoria_antiga: string
  categoria_nova: string
  delta_faturamento: string
  categoria_mudou: boolean
  rotulo: string
  delta_total: string
  aplicadas_iguais: number
  ids_aplicados: string[]
  regra_criada: boolean
  mensagem: string
}

export type Resposta = {
  categoria: string
  proposito?: string | null
  lembrar?: boolean
}

function novaChave(): string {
  return crypto.randomUUID()
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

export function confirmar(
  token: string,
  txId: string,
  resposta: Resposta,
  idempotencyKey?: string,
): Promise<ConfirmarResponse> {
  return api<ConfirmarResponse>(
    `/transacoes/${txId}/confirmar`,
    {
      method: 'PATCH',
      body: {
        categoria: resposta.categoria,
        proposito: resposta.proposito ?? null,
        lembrar: resposta.lembrar ?? false,
      },
      token,
      idempotencyKey: idempotencyKey ?? novaChave(),
    },
  )
}

// Corrige qualquer lancamento do usuario, mesmo ja classificado ou confirmado.
export function corrigir(
  token: string,
  txId: string,
  resposta: Resposta,
  idempotencyKey?: string,
): Promise<ConfirmarResponse> {
  return api<ConfirmarResponse>(
    `/transacoes/${txId}/corrigir`,
    {
      method: 'PATCH',
      body: {
        categoria: resposta.categoria,
        proposito: resposta.proposito ?? null,
        lembrar: resposta.lembrar ?? false,
      },
      token,
      idempotencyKey: idempotencyKey ?? novaChave(),
    },
  )
}