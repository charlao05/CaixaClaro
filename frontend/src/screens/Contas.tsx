import { useEffect, useRef, useState } from 'react'
import { PluggyConnect } from 'pluggy-connect-sdk'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  conectarBanco,
  listarContas,
  revogarConta,
  type Conta,
} from '../services/contas'
import {
  iniciarSync,
  consultarSync,
  type SyncStatus,
} from '../services/sync'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

const POLLING_MS = 2000
const TIMEOUT_CONTA_MS = 30000
const TIMEOUT_SYNC_MS = 120000

type SyncEstado = {
  contaId: string
  syncId: string
  status: SyncStatus
  erro: string | null
}

function formatData(iso: string): string {
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
  if (e instanceof Error) {
    return e.message
  }
  return 'Erro inesperado.'
}

function labelSync(s: SyncStatus): string {
  if (s === 'pendente') return 'Na fila'
  if (s === 'processando') return 'Sincronizando'
  if (s === 'completed') return 'Concluido'
  return 'Falhou'
}

export default function Contas({ sessao, onVoltar }: Props) {
  const [contas, setContas] = useState<Conta[] | null>(null)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)
  const [conectando, setConectando] = useState(false)
  const [erroConectar, setErroConectar] = useState<string | null>(null)
  const [aguardandoConta, setAguardandoConta] = useState(false)
  const [revogando, setRevogando] = useState<string | null>(null)
  const [syncAtivo, setSyncAtivo] = useState<SyncEstado | null>(null)
  const [erroSync, setErroSync] = useState<string | null>(null)

  const lengthAntesRef = useRef(0)
  const pluggyRef = useRef<{ destroy: () => Promise<void> } | null>(null)

  // 1. Carregamento inicial
  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const r = await listarContas(sessao.token)
        if (!ativo) return
        setContas(r.itens)
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

  // 2. Cleanup do widget quando o componente desmonta
  useEffect(() => {
    return () => {
      pluggyRef.current?.destroy().catch(() => {})
      pluggyRef.current = null
    }
  }, [])

  // 3. Polling enquanto aguarda o webhook item/created criar a conta
  useEffect(() => {
    if (!aguardandoConta) return
    const alvo = lengthAntesRef.current + 1

    const intervalId = setInterval(async () => {
      try {
        const r = await listarContas(sessao.token)
        if (r.itens.length >= alvo) {
          setContas(r.itens)
          setAguardandoConta(false)
        }
      } catch {
        // silencioso durante polling
      }
    }, POLLING_MS)

    const timeoutId = setTimeout(() => {
      setAguardandoConta(false)
      setErroConectar(
        'A conta não apareceu em 30s. Se você concluiu a autorização no banco, recarregue a página.',
      )
    }, TIMEOUT_CONTA_MS)

    return () => {
      clearInterval(intervalId)
      clearTimeout(timeoutId)
    }
  }, [aguardandoConta, sessao.token])

  // 4. Polling do sync ativo
  useEffect(() => {
    if (!syncAtivo) return
    if (syncAtivo.status === 'completed' || syncAtivo.status === 'failed') return

    const syncIdAtual = syncAtivo.syncId
    const contaIdAtual = syncAtivo.contaId

    const intervalId = setInterval(async () => {
      try {
        const r = await consultarSync(sessao.token, syncIdAtual)
        setSyncAtivo({
          contaId: contaIdAtual,
          syncId: r.sync_id,
          status: r.status,
          erro: r.erro,
        })
      } catch {
        // silencioso
      }
    }, POLLING_MS)

    const timeoutId = setTimeout(() => {
      setSyncAtivo(null)
      setErroSync(
        'Sync ainda nao terminou apos 2 min. Verifique em Transacoes se apareceram novos lancamentos.',
      )
    }, TIMEOUT_SYNC_MS)

    return () => {
      clearInterval(intervalId)
      clearTimeout(timeoutId)
    }
  }, [syncAtivo, sessao.token])

  // 5. Auto-limpar o estado de sync quando finaliza
  useEffect(() => {
    if (!syncAtivo) return
    if (syncAtivo.status !== 'completed' && syncAtivo.status !== 'failed') return
    const id = setTimeout(() => setSyncAtivo(null), 4000)
    return () => clearTimeout(id)
  }, [syncAtivo])

  async function handleConectar() {
    setErroConectar(null)
    setErroSync(null)
    setConectando(true)
    try {
      const { connect_token } = await conectarBanco(sessao.token)
      const instance = new PluggyConnect({
        connectToken: connect_token,
        includeSandbox: false,
        language: 'pt',
        theme: 'light',
        onSuccess: () => {
          lengthAntesRef.current = contas?.length ?? 0
          setAguardandoConta(true)
        },
        onError: (e) => {
          setErroConectar(
            e && e.message ? e.message : 'Erro no widget Pluggy.',
          )
        },
        onClose: () => {
          setConectando(false)
        },
      })
      pluggyRef.current = instance
      await instance.init()
    } catch (e) {
      setErroConectar(msgErro(e))
      setConectando(false)
    }
  }

  async function handleRevogar(contaId: string) {
    const ok = window.confirm(
      'Revogar esta conexão? As transações já importadas permanecem.',
    )
    if (!ok) return
    setErroConectar(null)
    setRevogando(contaId)
    try {
      await revogarConta(sessao.token, contaId)
      setContas((atual) => (atual ? atual.filter((c) => c.id !== contaId) : null))
    } catch (e) {
      setErroConectar(msgErro(e))
    } finally {
      setRevogando(null)
    }
  }

  async function handleSincronizar(contaId: string) {
    setErroSync(null)
    try {
      const r = await iniciarSync(sessao.token, contaId)
      setSyncAtivo({
        contaId,
        syncId: r.sync_id,
        status: r.status,
        erro: null,
      })
    } catch (e) {
      setErroSync(msgErro(e))
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

  if (!contas) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <h2>Contas bancárias</h2>

        {erroConectar && <p role="alert">{erroConectar}</p>}
        {erroSync && <p role="alert">{erroSync}</p>}

        {contas.length === 0 && !aguardandoConta && (
          <p>Nenhuma conta conectada.</p>
        )}

        {contas.length > 0 && (
          <ul className="contas-lista">
            {contas.map((c) => (
              <li key={c.id} className="conta-item">
                <div className="conta-info">
                  <strong>{c.nome}</strong>
                  <span className="conta-meta">
                    {c.provider} - {c.provider_account_id} - conectada em{' '}
                    {formatData(c.criado_em)}
                  </span>
                </div>

                <div className="conta-acoes">
                  <button
                    type="button"
                    onClick={() => handleSincronizar(c.id)}
                    disabled={
                      syncAtivo?.contaId === c.id &&
                      (syncAtivo.status === 'pendente' ||
                        syncAtivo.status === 'processando')
                    }
                  >
                    Sincronizar
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRevogar(c.id)}
                    disabled={revogando === c.id}
                  >
                    {revogando === c.id ? 'Revogando...' : 'Revogar'}
                  </button>
                </div>

                {syncAtivo?.contaId === c.id && (
                  <p className="conta-sync">
                    Sync: {labelSync(syncAtivo.status)}
                    {syncAtivo.erro ? ` - ${syncAtivo.erro}` : ''}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}

        {aguardandoConta && (
          <p className="conta-aguardando">
            Aguardando confirmacao do banco... a conta aparece assim que a
            Pluggy enviar o webhook.
          </p>
        )}

        <button
          type="button"
          className="conta-conectar"
          onClick={handleConectar}
          disabled={conectando || aguardandoConta}
        >
          {conectando
            ? 'Abrindo...'
            : aguardandoConta
              ? 'Aguardando...'
              : 'Conectar banco'}
        </button>
      </section>
    </main>
  )
}