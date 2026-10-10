import { api } from './api'
import type { OpcaoResposta } from './fila'

export type GrauCerteza =
  | 'fato_confirmado'
  | 'leitura_provavel'
  | 'duvida_declarada'

export type OpcaoEsclarecimento = {
  label: string
  proposito: string
  descricao: string
}

export type Opiniao = {
  tx_id: string
  data: string
  descricao: string
  valor: string
  origem?: string
  rotulo: string
  opcoes_correcao: OpcaoResposta[]
  fato: string
  interpretacao: string
  relacao_pf_pj: string
  possivel_tratamento_tributario: string
  condicoes_necessarias: string
  pendencias: string
  proximo_passo: string
  grau_certeza_leitura: GrauCerteza
  opcoes_esclarecimento: OpcaoEsclarecimento[]
  confirmada: boolean
}

export function getOpiniao(
  token: string,
  txId: string,
): Promise<Opiniao> {
  return api<Opiniao>(`/transacoes/${txId}/opiniao`, { token })
}