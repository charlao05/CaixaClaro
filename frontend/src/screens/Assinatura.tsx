import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  getStatus,
  checkout,
  pausar,
  listarPayments,
  type BillingStatusResponse,
  type CheckoutResponse,
  type PaymentItem,
  type Plano,
  type StatusPayment,
} from '../services/billing'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

const POLLING_MS = 3000
const TIMEOUT_CONFIRMACAO_MS = 60000

const PLANOS: { id: Plano; label: string; detalhe: string }[] = [
  { id: 'pro_mensal', label: 'Plano mensal', detalhe: 'R$ 49,90 a cada 30 dias' },
  { id: 'pro_anual', label: 'Plano anual', detalhe: 'R$ 499,00 a cada 365 dias' },
]

function formatData(iso: string | null): string {
  if (!iso) return '-'
  const partes = iso.slice(0, 10).split('-')
  if (partes.length !== 3) return iso
  return `${partes[2]}/${partes[1]}/${partes[0]}`
}

function msgErro(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter
      ? `${e.message} Tente novamente em ${e.retryAfter}s.`
      : e.message
  }
  if (e instanceof Error) return e.message
  return 'Erro inesperado.'
}

function labelStatusPayment(s: StatusPayment): string {
  if (s === 'pendente') return 'Aguardando pagamento'
  if (s === 'confirmado') return 'Confirmado'
  if (s === 'expirado') return 'Expirado'
  if (s === 'falhou') return 'Falhou'
  return 'Em reconciliacao'
}

export default function Assinatura({ sessao, onVoltar }: Props) {
  const [status, setStatus] = useState<BillingStatusResponse | null>(null)
  const [payments, setPayments] = useState<PaymentItem[] | null>(null)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)

  const [assinando, setAssinando] = useState<Plano | null>(null)
  const [erroAssinar, setErroAssinar] = useState<string | null>(null)
  const [checkoutAtivo, setCheckoutAtivo] = useState<CheckoutResponse | null>(null)
  const [copiado, setCopiado] = useState(false)

  const [pausando, setPausando] = useState(false)
  const [erroPausar, setErroPausar] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const [s, p] = await Promise.all([
          getStatus(sessao.token),
          listarPayments(sessao.token),
        ])
        if (!ativo) return
        setStatus(s)
        setPayments(p.itens)
      } catch (e) {
        if (!ativo) return
        setErroCarregar(msgErro(e))
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [sessao.token])

  useEffect(() => {
    if (!copiado) return
    const id = setTimeout(() => setCopiado(false), 2000)
    return () => clearTimeout(id)
  }, [copiado])

  // Polling enquanto aguarda confirmacao do pagamento
  useEffect(() => {
    if (!checkoutAtivo) return
    if (checkoutAtivo.status === 'confirmado') return

    const intervalId = setInterval(async () => {
      try {
        const s = await getStatus(sessao.token)
        setStatus(s)
        if (s.ultimo_payment?.status === 'confirmado') {
          setCheckoutAtivo(null)
          const p = await listarPayments(sessao.token)
          setPayments(p.itens)
        }
      } catch {
        // silencioso durante polling
      }
    }, POLLING_MS)

    const timeoutId = setTimeout(() => {
      setCheckoutAtivo(null)
    }, TIMEOUT_CONFIRMACAO_MS)

    return () => {
      clearInterval(intervalId)
      clearTimeout(timeoutId)
    }
  }, [checkoutAtivo, sessao.token])

  async function handleAssinar(plano: Plano) {
    setErroAssinar(null)
    setAssinando(plano)
    try {
      const r = await checkout(sessao.token, plano)
      setCheckoutAtivo(r)
    } catch (e) {
      setErroAssinar(msgErro(e))
    } finally {
      setAssinando(null)
    }
  }

  async function handleCopiar() {
    if (!checkoutAtivo?.pix_copy_paste) return
    try {
      await navigator.clipboard.writeText(checkoutAtivo.pix_copy_paste)
      setCopiado(true)
    } catch {
      setErroAssinar('Nao foi possivel copiar o codigo Pix.')
    }
  }

  async function handlePausar() {
    const ok = window.confirm(
      'Pausar a assinatura? Voce nao sera cobrado enquanto pausada.',
    )
    if (!ok) return
    setErroPausar(null)
    setPausando(true)
    try {
      await pausar(sessao.token, null)
      const s = await getStatus(sessao.token)
      setStatus(s)
    } catch (e) {
      setErroPausar(msgErro(e))
    } finally {
      setPausando(false)
    }
  }

  const cabecalho = (
    <header>
      <h1>CaixaClaro</h1>
      <div>
        <span>{sessao.user.email}</span>
        <button type="button" onClick={onVoltar}>
          Voltar ao painel
        </button>
      </div>
    </header>
  )

  if (erroCarregar) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p role="alert">{erroCarregar}</p>
      </main>
    )
  }

  if (!status || !payments) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  const sub = status.subscription
  const ultimo = status.ultimo_payment

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <h2>Assinatura</h2>

        {erroPausar && <p role="alert">{erroPausar}</p>}

        {sub === null ? (
          <div>
            <p>Voce nao tem assinatura ativa.</p>
            <p className="assinatura-nota">
              Valores placeholder do backend; serao definidos antes do lancamento.
            </p>
            <div className="assinatura-planos">
              {PLANOS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="assinatura-plano"
                  onClick={() => handleAssinar(p.id)}
                  disabled={assinando !== null}
                >
                  <strong>{p.label}</strong>
                  <span>{p.detalhe}</span>
                </button>
              ))}
            </div>
            {erroAssinar && <p role="alert">{erroAssinar}</p>}
          </div>
        ) : (
          <div className="assinatura-ativa">
            <p>
              <strong>Plano:</strong> {sub.plano}
            </p>
            <p>
              <strong>Status:</strong> {sub.status}
            </p>
            <p>
              <strong>Periodo:</strong> {formatData(sub.periodo_inicio)} ate{' '}
              {formatData(sub.periodo_fim)}
            </p>
            {sub.pausada_ate && (
              <p>
                <strong>Pausada ate:</strong> {formatData(sub.pausada_ate)}
              </p>
            )}
            {sub.status === 'ativa' && (
              <button
                type="button"
                onClick={handlePausar}
                disabled={pausando}
              >
                {pausando ? 'Pausando...' : 'Pausar assinatura'}
              </button>
            )}
          </div>
        )}
      </section>

      {checkoutAtivo && (
        <section>
          <h2>Pagamento Pix</h2>
          {checkoutAtivo.pix_qr_code && (
            <img
              className="assinatura-qr"
              src={`data:image/png;base64,${checkoutAtivo.pix_qr_code}`}
              alt="QR code Pix"
            />
          )}
          {checkoutAtivo.pix_copy_paste && (
            <>
              <p>Ou copie o codigo Pix:</p>
              <code className="assinatura-payload">
                {checkoutAtivo.pix_copy_paste}
              </code>
              <div className="assinatura-acoes">
                <button type="button" onClick={handleCopiar}>
                  {copiado ? 'Copiado!' : 'Copiar codigo'}
                </button>
              </div>
            </>
          )}
          <p className="assinatura-nota">
            Aguardando confirmacao do pagamento... a tela atualiza sozinha.
          </p>
        </section>
      )}

      <section>
        <h2>Pagamentos</h2>

        {ultimo && (
          <p className="assinatura-ultimo">
            Ultimo pagamento: {labelStatusPayment(ultimo.status)} —{' '}
            {formatData(ultimo.criado_em)}
          </p>
        )}

        {payments.length === 0 ? (
          <p>Nenhum pagamento registrado.</p>
        ) : (
          <ul className="pagamentos-lista">
            {payments.map((p) => (
              <li key={p.id} className="pagamento-item">
                <span className="pagamento-plano">{p.plano}</span>
                <span className="pagamento-valor">R$ {p.valor}</span>
                <span className="pagamento-status">
                  {labelStatusPayment(p.status)}
                </span>
                <span className="pagamento-data">{formatData(p.criado_em)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}