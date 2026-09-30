import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import type { Regime } from '../services/auth'
import {
  getPerfil,
  atualizarPerfil,
  type Perfil as DadosPerfil,
} from '../services/perfil'
import {
  gerarTokenVinculacao,
  type TokenVinculacaoResponse,
} from '../services/telegram'

type Props = {
  sessao: Sessao
  onVoltar: () => void
  onAtualizarUsuario: (nome: string | null, regime: Regime) => void
}

const REGIMES: { id: Regime; label: string }[] = [
  { id: 'MEI', label: 'MEI (Microempreendedor Individual)' },
  { id: 'SIMPLES', label: 'Simples Nacional' },
  { id: 'PF', label: 'Pessoa Física' },
]

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME

function formatData(iso: string): string {
  const partes = iso.slice(0, 10).split('-')
  if (partes.length !== 3) return iso
  return `${partes[2]}/${partes[1]}/${partes[0]}`
}

function formatHora(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

function minutosAte(iso: string, agora: number): number {
  const t = new Date(iso).getTime()
  if (isNaN(t)) return 0
  return Math.max(0, Math.floor((t - agora) / 60000))
}

function msgErro(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter
      ? `${e.message} Tente novamente em ${e.retryAfter}s.`
      : e.message
  }
  return 'Erro inesperado.'
}

export default function Perfil({ sessao, onVoltar, onAtualizarUsuario }: Props) {
  const [perfil, setPerfil] = useState<DadosPerfil | null>(null)
  const [nome, setNome] = useState('')
  const [regime, setRegime] = useState<Regime>(sessao.user.regime)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)
  const [erroSalvar, setErroSalvar] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [ok, setOk] = useState(false)

  const [tokenResp, setTokenResp] = useState<TokenVinculacaoResponse | null>(null)
  const [gerandoToken, setGerandoToken] = useState(false)
  const [erroTelegram, setErroTelegram] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)
  const [verificando, setVerificando] = useState(false)
  const [msgVerificacao, setMsgVerificacao] = useState<string | null>(null)
  const [agora, setAgora] = useState(() => Date.now())

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const p = await getPerfil(sessao.token)
        if (!ativo) return
        setPerfil(p)
        setNome(p.nome ?? '')
        setRegime(p.regime)
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
    if (!ok) return
    const id = setTimeout(() => setOk(false), 2500)
    return () => clearTimeout(id)
  }, [ok])

  useEffect(() => {
    if (!copiado) return
    const id = setTimeout(() => setCopiado(false), 2000)
    return () => clearTimeout(id)
  }, [copiado])

  useEffect(() => {
    if (!tokenResp) return
    const id = setInterval(() => setAgora(Date.now()), 10000)
    return () => clearInterval(id)
  }, [tokenResp])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErroSalvar(null)
    setOk(false)
    setSalvando(true)
    try {
      const nomeFinal = nome.trim() === '' ? null : nome.trim()
      await atualizarPerfil(sessao.token, { nome: nomeFinal, regime })
      const atualizado = await getPerfil(sessao.token)
      setPerfil(atualizado)
      setNome(atualizado.nome ?? '')
      setRegime(atualizado.regime)
      onAtualizarUsuario(atualizado.nome, atualizado.regime)
      setOk(true)
    } catch (e) {
      setErroSalvar(msgErro(e))
    } finally {
      setSalvando(false)
    }
  }

  async function handleGerarToken() {
    setErroTelegram(null)
    setMsgVerificacao(null)
    setGerandoToken(true)
    try {
      const r = await gerarTokenVinculacao(sessao.token)
      setTokenResp(r)
      setAgora(Date.now())
    } catch (e) {
      setErroTelegram(msgErro(e))
    } finally {
      setGerandoToken(false)
    }
  }

  async function handleCopiar() {
    if (!tokenResp) return
    try {
      await navigator.clipboard.writeText(`/start ${tokenResp.token}`)
      setCopiado(true)
    } catch {
      setErroTelegram('Não foi possível copiar o comando.')
    }
  }

  function handleAbrirTelegram() {
    if (!tokenResp || !BOT_USERNAME) return
    const url = `https://t.me/${BOT_USERNAME}?start=${encodeURIComponent(tokenResp.token)}`
    window.open(url, '_blank', 'noopener')
  }

  async function handleVerificar() {
    setMsgVerificacao(null)
    setErroTelegram(null)
    setVerificando(true)
    try {
      const p = await getPerfil(sessao.token)
      setPerfil(p)
      if (p.telegram_chat_id === null) {
        setMsgVerificacao(
          'Ainda não detectamos a conexão. Confirme que enviou /start com o código correto para o Telegram.',
        )
      }
    } catch (e) {
      setErroTelegram(msgErro(e))
    } finally {
      setVerificando(false)
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

  if (!perfil) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  const expirado =
    tokenResp !== null &&
    new Date(tokenResp.expira_em).getTime() < agora

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <h2>Perfil</h2>

        <form onSubmit={handleSubmit} className="perfil-form">
          <label>
            E-mail
            <input type="text" value={perfil.email} readOnly disabled />
          </label>

          <label>
            Nome
            <input
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={100}
              disabled={salvando}
              placeholder="Como quer ser chamado"
            />
          </label>

          <label>
            Regime
            <select
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime)}
              disabled={salvando}
            >
              {REGIMES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Criado em
            <input
              type="text"
              value={formatData(perfil.criado_em)}
              readOnly
              disabled
            />
          </label>

          {erroSalvar && <p role="alert">{erroSalvar}</p>}
          {ok && (
            <p role="status" className="perfil-ok">
              Perfil atualizado.
            </p>
          )}

          <button type="submit" disabled={salvando}>
            {salvando ? 'Salvando...' : 'Salvar alterações'}
          </button>
        </form>
      </section>

      <section>
        <h2>Telegram</h2>

        {perfil.telegram_chat_id !== null ? (
          <div className="telegram-vinculado">
            <p>
              <strong>Conectado</strong> — você vai receber alertas de
              faturamento e do boleto mensal do MEI (DAS) no Telegram.
            </p>
          </div>
        ) : (
          <div className="telegram-vincular">
            <p>
              Receba alertas de faturamento e do boleto mensal do MEI (DAS) no Telegram.
            </p>

            {erroTelegram && <p role="alert">{erroTelegram}</p>}

            {!tokenResp && (
              <button
                type="button"
                onClick={handleGerarToken}
                disabled={gerandoToken}
              >
                {gerandoToken ? 'Gerando...' : 'Conectar Telegram'}
              </button>
            )}

            {tokenResp && (
              <>
                <p>
                  Envie o comando abaixo para o bot{' '}
                  {BOT_USERNAME && <code>@{BOT_USERNAME}</code>}:
                </p>
                <code className="telegram-token">
                  /start {tokenResp.token}
                </code>

                <div className="telegram-acoes">
                  <button type="button" onClick={handleCopiar}>
                    {copiado ? 'Copiado!' : 'Copiar comando'}
                  </button>
                  {BOT_USERNAME && (
                    <button type="button" onClick={handleAbrirTelegram}>
                      Abrir Telegram
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleVerificar}
                    disabled={verificando}
                  >
                    {verificando ? 'Verificando...' : 'Já conectei — verificar'}
                  </button>
                </div>

                {expirado ? (
                  <p className="telegram-expirado">
                    Token expirado.{' '}
                    <button type="button" onClick={handleGerarToken}>
                      Gerar novo
                    </button>
                  </p>
                ) : (
                  <p className="telegram-prazo">
                    Expira as {formatHora(tokenResp.expira_em)} (~
                    {minutosAte(tokenResp.expira_em, agora)} min)
                  </p>
                )}

                {msgVerificacao && (
                  <p className="telegram-msg">{msgVerificacao}</p>
                )}
              </>
            )}
          </div>
        )}
      </section>
    </main>
  )
}