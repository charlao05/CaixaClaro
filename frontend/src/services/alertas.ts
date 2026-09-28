import { api, type Paginado } from './api'

export type Alerta = {
  id: string
  tipo: string
  severidade: string
  mensagem: string
  lido_em: string | null
  criado_em: string
  banda_ou_slug: string
  prazo: string | null
}

export type ListarAlertasOpts = {
  apenasNaoLidos?: boolean
  tipo?: string
  limite?: number
  cursor?: string
}

export type MarcarLidoResponse = {
  alerta_id: string
  marcado_agora: boolean
}

export function listarAlertas(
  token: string,
  opts: ListarAlertasOpts = {},
): Promise<Paginado<Alerta>> {
  const params = new URLSearchParams()
  if (opts.apenasNaoLidos) params.set('apenas_nao_lidos', 'true')
  if (opts.tipo) params.set('tipo', opts.tipo)
  if (opts.limite !== undefined) params.set('limite', String(opts.limite))
  if (opts.cursor) params.set('cursor', opts.cursor)
  const qs = params.toString()
  const path = qs ? `/transacoes/alertas?${qs}` : '/transacoes/alertas'
  return api<Paginado<Alerta>>(path, { token })
}

export function marcarAlertaLido(
  token: string,
  alertaId: string,
): Promise<MarcarLidoResponse> {
  return api<MarcarLidoResponse>(
    `/transacoes/alertas/${alertaId}/lido`,
    { method: 'POST', token },
  )
}