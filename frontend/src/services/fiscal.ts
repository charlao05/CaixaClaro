import { api } from './api'

export type FaixaResumo = {
  slug: string
  percentual: number
  severidade: string
  limiar: string
  atingida: boolean
}

export type ProximaFaixa = {
  slug: string
  percentual: number
  limiar: string
  falta: string
}

export type FiscalResumo = {
  ano_referencia: number
  faturamento_acumulado: string
  teto_anual: string
  percentual_consumido: number
  banda_atual: string | null
  ultima_avaliacao_em: string | null
  faixas: FaixaResumo[]
  proxima_faixa: ProximaFaixa | null
  alertas_nao_lidos: number
  tem_transacoes: boolean
}

export function getResumo(token: string): Promise<FiscalResumo> {
  return api<FiscalResumo>('/transacoes/fiscal/resumo', { token })
}