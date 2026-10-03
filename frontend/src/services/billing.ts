import { api } from './api'

export type Plano = 'pro_mensal' | 'pro_anual'

export type StatusSubscription = 'ativa' | 'pausada'

export type StatusPayment =
  | 'pendente'
  | 'confirmado'
  | 'expirado'
  | 'falhou'
  | 'pendente_reconciliacao'

export type Subscription = {
  plano: string
  status: StatusSubscription
  periodo_inicio: string | null
  periodo_fim: string | null
  pausada_ate: string | null
}

export type UltimoPayment = {
  id: string
  status: StatusPayment
  tem_qr: boolean
  criado_em: string
}

export type BillingStatusResponse = {
  subscription: Subscription | null
  ultimo_payment: UltimoPayment | null
}

export type MetodoPagamento = 'pix' | 'cartao'

export type CheckoutResponse = {
  payment_id: string
  metodo: MetodoPagamento
  status: StatusPayment
  pix_qr_code: string | null
  pix_copy_paste: string | null
  invoice_url: string | null
}

export type PaymentItem = {
  id: string
  plano: string
  valor: string
  periodo_dias: number
  status: StatusPayment
  asaas_payment_id: string | null
  criado_em: string
}

export type ListarPaymentsResponse = {
  itens: PaymentItem[]
}

export type PausarResponse = {
  ok: true
  status: 'pausada'
  pausada_ate: string | null
}

function novaChave(): string {
  return crypto.randomUUID()
}

export function getStatus(token: string): Promise<BillingStatusResponse> {
  return api<BillingStatusResponse>('/billing/status', { token })
}

export function checkout(
  token: string,
  plano: Plano,
  metodo: MetodoPagamento,
  idempotencyKey?: string,
): Promise<CheckoutResponse> {
  return api<CheckoutResponse>('/billing/checkout', {
    method: 'POST',
    body: { plano, metodo },
    token,
    idempotencyKey: idempotencyKey ?? novaChave(),
  })
}

export function pausar(
  token: string,
  pausadaAte: string | null,
): Promise<PausarResponse> {
  return api<PausarResponse>('/billing/pausar', {
    method: 'POST',
    body: { pausada_ate: pausadaAte },
    token,
  })
}

export function listarPayments(token: string): Promise<ListarPaymentsResponse> {
  return api<ListarPaymentsResponse>('/payments', { token })
}