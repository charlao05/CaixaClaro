import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  getStatus,
  checkout,
  pausar,
  listarPayments,
  type Acesso,
  type BillingStatusResponse,
  type CheckoutResponse,
  type MetodoPagamento,
  type PaymentItem,
  type Plano,
  type StatusPayment,
  type Subscription,
} from '../services/billing'

type Props = {
  sessao: Sessao
  onVoltar: () => void
  onLogout: () => void
}

// A tela confere o pagamento sozinha a cada 5 s, por 10 minutos. Depois
// disso para de conferir, mas a cobrança continua na tela, com um botão
// para conferir na hora. (Antes o QR sumia depois de 60 segundos.)
const POLLING_MS = 5000
const POLLING_MAX_MS = 10 * 60 * 1000

// Mesma janela em que o backend passa a aceitar a renovação
// (CONTRATOS_INTERNOS §12: periodo_fim <= hoje + 3 dias).
const JANELA_RENOVACAO_MS = 3 * 24 * 60 * 60 * 1000

const PLANOS: { id: Plano; label: string; detalhe: string }[] = [
  { id: 'pro_mensal', label: 'Plano mensal', detalhe: 'R$ 29,90 a cada 30 dias' },
  { id: 'pro_anual', label: 'Plano anual', detalhe: 'R$ 299,00 a cada 365 dias' },
]

const NOME_PLANO: Record<string, string> = {
  pro_mensal: 'Plano mensal',
  pro_anual: 'Plano anual',
}

const NOME_METODO: Record<MetodoPagamento, string> = {
  pix: 'Pix',
  cartao: 'Cartão',
}

function ehPlano(valor: string): valor is Plano {
  return valor === 'pro_mensal' || valor === 'pro_anual'
}

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

/** Data pura (AAAA-MM-DD), sem horário: não passa por fuso. */
function formatData(iso: string | null): string {
  if (!iso) return '-'
  const partes = iso.slice(0, 10).split('-')
  if (partes.length !== 3) return iso
  return `${partes[2]}/${partes[1]}/${partes[0]}`
}

/** Instante (data e hora com fuso): mostra o dia no relógio de quem lê. */
function formatDia(iso: string | null): string {
  if (!iso) return '-'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return formatData(iso)
  return new Date(t).toLocaleDateString('pt-BR')
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
  if (s === 'expirado') return 'Prazo encerrado'
  if (s === 'falhou') return 'Não concluído'
  if (s === 'cancelado') return 'Cancelado'
  return 'Aguardando confirmação'
}

/** Uma frase que diz ao usuário por que ele está vendo esta tela. */
function fraseDoAcesso(acesso: Acesso, sub: Subscription | null): string | null {
  if (acesso.situacao === 'teste') {
    return (
      `Você está no período de teste, que vai até ${formatDia(acesso.teste_ate)}. ` +
      'Depois disso, é preciso assinar para continuar usando.'
    )
  }
  if (acesso.situacao === 'trial_expirado') {
    return (
      `Seu período de teste acabou em ${formatDia(acesso.teste_ate)}. ` +
      'Para continuar usando o CaixaClaro, escolha um plano abaixo. ' +
      'O que você já trouxe continua guardado.'
    )
  }
  if (acesso.situacao === 'assinatura_expirada') {
    return (
      `Sua assinatura venceu em ${formatDia(sub?.periodo_fim ?? null)}. ` +
      'Para voltar a usar o CaixaClaro, renove abaixo. ' +
      'O que você já trouxe continua guardado.'
    )
  }
  if (acesso.situacao === 'isento') {
    return 'Sua conta está com o acesso liberado.'
  }
  return null
}

export default function Assinatura({ sessao, onVoltar, onLogout }: Props) {
  const [status, setStatus] = useState<BillingStatusResponse | null>(null)
  const [payments, setPayments] = useState<PaymentItem[] | null>(null)
  const [agora, setAgora] = useState<number>(() => Date.now())
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)

  const [assinando, setAssinando] = useState<Plano | null>(null)
  const [erroAssinar, setErroAssinar] = useState<string | null>(null)
  const [checkoutAtivo, setCheckoutAtivo] = useState<CheckoutResponse | null>(null)
  const [conferindoSozinha, setConferindoSozinha] = useState(false)
  const [verificando, setVerificando] = useState(false)
  const [avisoPagamento, setAvisoPagamento] = useState<string | null>(null)
  const [metodo, setMetodo] = useState<MetodoPagamento>('pix')
  const [copiado, setCopiado] = useState(false)

  const [pausando, setPausando] = useState(false)
  const [erroPausar, setErroPausar] = useState<string | null>(null)

  const secaoPagamento = useRef<HTMLElement | null>(null)

  const buscar = useCallback(async () => {
    const [s, p] = await Promise.all([
      getStatus(sessao.token),
      listarPayments(sessao.token),
    ])
    return { s, itens: p.itens }
  }, [sessao.token])

  const recarregar = useCallback(async () => {
    const dados = await buscar()
    setStatus(dados.s)
    setPayments(dados.itens)
    setAgora(Date.now())
    return dados
  }, [buscar])

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const dados = await buscar()
        if (!ativo) return
        setStatus(dados.s)
        setPayments(dados.itens)
        setAgora(Date.now())
      } catch (e) {
        if (!ativo) return
        setErroCarregar(msgErro(e))
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [buscar])

  useEffect(() => {
    if (!copiado) return
    const id = setTimeout(() => setCopiado(false), 2000)
    return () => clearTimeout(id)
  }, [copiado])

  /**
   * Confere a cobrança que está na tela pelo ID dela — não pelo "último
   * pagamento", que pode ser outro (uma renovação gerada depois, por exemplo).
   */
  const conferirPagamento = useCallback(
    async (paymentId: string): Promise<StatusPayment | null> => {
      const { s, itens } = await recarregar()
      const item = itens.find((i) => i.id === paymentId)
      if (!item) return null
      if (item.status === 'confirmado') {
        setCheckoutAtivo(null)
        setErroAssinar(null)
        setAvisoPagamento(
          s.subscription?.periodo_fim
            ? `Pagamento confirmado. Sua assinatura vale até ${formatDia(s.subscription.periodo_fim)}.`
            : 'Pagamento confirmado.',
        )
      } else if (item.status === 'expirado') {
        setCheckoutAtivo(null)
        setErroAssinar('O prazo desta cobrança passou. Gere outra abaixo.')
      } else if (item.status === 'cancelado' || item.status === 'falhou') {
        setCheckoutAtivo(null)
        setErroAssinar(
          'Esta cobrança não vale mais. Escolha de novo o plano e a forma de pagamento.',
        )
      }
      return item.status
    },
    [recarregar],
  )

  const idEmAcompanhamento = checkoutAtivo?.payment_id ?? null

  useEffect(() => {
    if (!idEmAcompanhamento) return

    const intervalId = setInterval(() => {
      conferirPagamento(idEmAcompanhamento).catch(() => {
        // silencioso: a próxima conferência tenta de novo
      })
    }, POLLING_MS)
    const timeoutId = setTimeout(() => {
      clearInterval(intervalId)
      setConferindoSozinha(false)
    }, POLLING_MAX_MS)

    return () => {
      clearInterval(intervalId)
      clearTimeout(timeoutId)
    }
  }, [idEmAcompanhamento, conferirPagamento])

  useEffect(() => {
    if (!idEmAcompanhamento) return
    secaoPagamento.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [idEmAcompanhamento])

  async function handleAssinar(plano: Plano, forma: MetodoPagamento) {
    setErroAssinar(null)
    setAvisoPagamento(null)
    setAssinando(plano)
    try {
      const r = await checkout(sessao.token, plano, forma)
      setCheckoutAtivo(r)
      setConferindoSozinha(true)
      // A cobrança nova precisa aparecer na lista de pagamentos.
      recarregar().catch(() => {})
    } catch (e) {
      setErroAssinar(msgErro(e))
    } finally {
      setAssinando(null)
    }
  }

  async function handleVerificar() {
    if (!checkoutAtivo) return
    setVerificando(true)
    setErroAssinar(null)
    try {
      const situacao = await conferirPagamento(checkoutAtivo.payment_id)
      if (situacao === 'pendente' || situacao === 'pendente_reconciliacao') {
        setErroAssinar(
          'O pagamento ainda não foi confirmado. Se você acabou de pagar, espere um instante e confira de novo.',
        )
      }
    } catch (e) {
      setErroAssinar(msgErro(e))
    } finally {
      setVerificando(false)
    }
  }

  async function handleCopiar() {
    if (!checkoutAtivo?.pix_copy_paste) return
    try {
      await navigator.clipboard.writeText(checkoutAtivo.pix_copy_paste)
      setCopiado(true)
    } catch {
      setErroAssinar('Não foi possível copiar o código Pix.')
    }
  }

  async function handlePausar() {
    const ok = window.confirm(
      'Pausar a assinatura? Você não será cobrado enquanto pausada.',
    )
    if (!ok) return
    setErroPausar(null)
    setPausando(true)
    try {
      await pausar(sessao.token, null)
      await recarregar()
    } catch (e) {
      setErroPausar(msgErro(e))
    } finally {
      setPausando(false)
    }
  }

  // `acesso` é opcional só para tolerar um backend mais antigo que a tela.
  const acesso: Acesso | null = status?.acesso ?? null
  const bloqueado = acesso !== null && !acesso.liberado

  const cabecalho = (
    <header>
      <h1>CaixaClaro</h1>
      <div>
        <span>{sessao.user.email}</span>
        {bloqueado ? (
          // Com o acesso bloqueado o painel devolve para cá; o que resta é sair.
          <button type="button" onClick={onLogout}>
            Sair
          </button>
        ) : (
          <button type="button" onClick={onVoltar}>
            Voltar ao painel
          </button>
        )}
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

  // No backend, 'ativa' quer dizer "habilitada para renovação", e não
  // "período em dia" (DECISOES 2026-09-26). Quem diz se está em dia é a data.
  const fimMs = sub?.periodo_fim ? Date.parse(sub.periodo_fim) : NaN
  const temFim = Number.isFinite(fimMs)
  const vencida = sub !== null && temFim && fimMs <= agora
  const pertoDoFim = sub !== null && temFim && fimMs - agora <= JANELA_RENOVACAO_MS
  const pausada = sub?.status === 'pausada'
  const podePagar = sub === null || !temFim || vencida || pertoDoFim || pausada

  const situacaoDaAssinatura = pausada
    ? 'Pausada'
    : vencida
      ? `Vencida em ${formatDia(sub?.periodo_fim ?? null)}`
      : `Em dia até ${formatDia(sub?.periodo_fim ?? null)}`

  const frase = acesso ? fraseDoAcesso(acesso, sub) : null

  // Cobrança esperando pagamento que não está aberta na tela (a de uma
  // renovação, ou a de antes de recarregar a página).
  const pendente =
    payments.find(
      (p) => p.status === 'pendente' && p.id !== checkoutAtivo?.payment_id,
    ) ?? null
  const planoPendente = pendente && ehPlano(pendente.plano) ? pendente.plano : null

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <h2>Assinatura</h2>

        {frase && (
          <p role="status" className="assinatura-aviso">
            {frase}
          </p>
        )}
        {avisoPagamento && (
          <p role="status" className="revisao-feedback">
            {avisoPagamento}
          </p>
        )}
        {erroPausar && <p role="alert">{erroPausar}</p>}

        {sub === null ? (
          !frase && <p>Você não tem assinatura.</p>
        ) : (
          <div className="assinatura-ativa">
            <p>
              <strong>Plano:</strong> {NOME_PLANO[sub.plano] ?? sub.plano}
            </p>
            <p>
              <strong>Situação:</strong> {situacaoDaAssinatura}
            </p>
            <p>
              <strong>Período:</strong> {formatDia(sub.periodo_inicio)} até{' '}
              {formatDia(sub.periodo_fim)}
            </p>
            {sub.pausada_ate && (
              <p>
                <strong>Pausada até:</strong> {formatData(sub.pausada_ate)}
              </p>
            )}
            {pausada && (
              <p className="assinatura-nota">
                Com a assinatura pausada o CaixaClaro não gera cobrança de
                renovação. Para voltar, faça um pagamento abaixo.
              </p>
            )}
            {!podePagar && (
              <p className="assinatura-nota">
                Perto do vencimento, a opção de renovar aparece aqui.
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

      {pendente && planoPendente && (
        <section>
          <h2>Você tem um pagamento esperando</h2>
          <p>
            {NOME_PLANO[pendente.plano] ?? pendente.plano} ·{' '}
            {formatBRL(pendente.valor)} · {NOME_METODO[pendente.metodo] ?? pendente.metodo}{' '}
            · gerado em {formatDia(pendente.criado_em)}
          </p>
          <div className="assinatura-acoes">
            <button
              type="button"
              onClick={() => handleAssinar(planoPendente, pendente.metodo)}
              disabled={assinando !== null}
            >
              {assinando === planoPendente ? 'Abrindo...' : 'Ver como pagar'}
            </button>
          </div>
        </section>
      )}

      {podePagar && (
        <section>
          <h2>{sub === null ? 'Assinar' : 'Renovar'}</h2>
          {sub !== null && (
            <p>
              O novo período começa quando o atual termina — ou hoje, se ele
              já terminou.
            </p>
          )}
          <p className="assinatura-nota">
            Valores provisórios; serão definidos antes do lançamento do plano.
          </p>
          <fieldset className="assinatura-metodo">
            <legend>Forma de pagamento</legend>
            <label>
              <input
                type="radio"
                name="metodo"
                value="pix"
                checked={metodo === 'pix'}
                onChange={() => setMetodo('pix')}
                disabled={assinando !== null}
              />
              Pix
            </label>
            <label>
              <input
                type="radio"
                name="metodo"
                value="cartao"
                checked={metodo === 'cartao'}
                onChange={() => setMetodo('cartao')}
                disabled={assinando !== null}
              />
              Cartão
            </label>
          </fieldset>
          <div className="assinatura-planos">
            {PLANOS.map((p) => (
              <button
                key={p.id}
                type="button"
                className="assinatura-plano"
                onClick={() => handleAssinar(p.id, metodo)}
                disabled={assinando !== null}
              >
                <strong>{p.label}</strong>
                <span>{p.detalhe}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {erroAssinar && <p role="alert">{erroAssinar}</p>}

      {checkoutAtivo && (
        <section ref={secaoPagamento}>
          {checkoutAtivo.metodo === 'pix' ? (
            <>
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
                  <p>Ou copie o código Pix:</p>
                  <code className="assinatura-payload">
                    {checkoutAtivo.pix_copy_paste}
                  </code>
                </>
              )}
            </>
          ) : (
            <>
              <h2>Pagamento com cartão</h2>
              {checkoutAtivo.invoice_url ? (
                <p>
                  Você será levado à página segura do Asaas para concluir o
                  pagamento. Nenhum dado do cartão passa pelo CaixaClaro.
                </p>
              ) : (
                <p role="alert">
                  Não foi possível obter o link de pagamento. Tente novamente.
                </p>
              )}
            </>
          )}

          <div className="assinatura-acoes">
            {checkoutAtivo.metodo === 'pix' && checkoutAtivo.pix_copy_paste && (
              <button type="button" onClick={handleCopiar}>
                {copiado ? 'Copiado!' : 'Copiar código'}
              </button>
            )}
            {checkoutAtivo.metodo === 'cartao' && checkoutAtivo.invoice_url && (
              <a
                className="assinatura-botao"
                href={checkoutAtivo.invoice_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ir para o pagamento
              </a>
            )}
            <button type="button" onClick={handleVerificar} disabled={verificando}>
              {verificando ? 'Conferindo...' : 'Já paguei — conferir agora'}
            </button>
            <button type="button" onClick={() => setCheckoutAtivo(null)}>
              Fechar
            </button>
          </div>

          <p className="assinatura-nota">
            {conferindoSozinha
              ? 'Aguardando a confirmação do pagamento... esta tela confere sozinha.'
              : 'Esta tela parou de conferir sozinha. Depois de pagar, use "Já paguei — conferir agora".'}{' '}
            Se fechar, a cobrança continua valendo e aparece em "Você tem um
            pagamento esperando".
          </p>
        </section>
      )}

      <section>
        <h2>Pagamentos</h2>

        {ultimo && (
          <p className="assinatura-ultimo">
            Último pagamento: {labelStatusPayment(ultimo.status)} —{' '}
            {formatDia(ultimo.criado_em)}
          </p>
        )}

        {payments.length === 0 ? (
          <p>Nenhum pagamento registrado.</p>
        ) : (
          <ul className="pagamentos-lista">
            {payments.map((p) => (
              <li key={p.id} className="pagamento-item">
                <span className="pagamento-plano">
                  {NOME_PLANO[p.plano] ?? p.plano} · {NOME_METODO[p.metodo] ?? p.metodo}
                </span>
                <span className="pagamento-valor">{formatBRL(p.valor)}</span>
                <span className="pagamento-status">
                  {labelStatusPayment(p.status)}
                </span>
                <span className="pagamento-data">{formatDia(p.criado_em)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
