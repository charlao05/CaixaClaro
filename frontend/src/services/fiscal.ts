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
  regime: 'MEI' | 'SIMPLES' | 'PF'
  faturamento_acumulado: string
  // null quando a pessoa nao e MEI: nao existe limite de MEI para mostrar.
  teto_anual: string | null
  limite_proporcional: boolean
  percentual_consumido: number | null
  banda_atual: string | null
  ultima_avaliacao_em: string | null
  faixas: FaixaResumo[]
  proxima_faixa: ProximaFaixa | null
  alertas_nao_lidos: number
  tem_transacoes: boolean
  total_lancamentos: number
  pendentes_revisao: number
  mes_referencia: string | null
  entradas_mes: string | null
  saidas_mes: string | null
}

export function getResumo(token: string): Promise<FiscalResumo> {
  return api<FiscalResumo>('/transacoes/fiscal/resumo', { token })
}