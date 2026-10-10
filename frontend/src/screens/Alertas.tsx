import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import { listarAlertas, marcarAlertaLido, type Alerta } from '../services/alertas'

type Props = {
  sessao: Sessao
  onVoltar: () => void
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
  return 'Erro inesperado.'
}

const ROTULO_SEVERIDADE: Record<string, string> = {
  informativo: 'Aviso',
  atencao: 'Atenção',
  critico: 'Importante',
}

function classeSeveridade(sev: string): string {
  const s = sev.toLowerCase()
  if (s.includes('critic') || s.includes('alert') || s.includes('perigo')) {
    return 'alerta-sev critico'
  }
  if (s.includes('aten') || s.includes('avis')) {
    return 'alerta-sev atencao'
  }
  return 'alerta-sev informativo'
}

export default function Alertas({ sessao, onVoltar }: Props) {
  const [apenasNaoLidos, setApenasNaoLidos] = useState(true)
  const [itens, setItens] = useState<Alerta[] | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [marcando, setMarcando] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const r = await listarAlertas(sessao.token, {
          apenasNaoLidos,
          limite: 100,
        })
        if (!ativo) return
        setItens(r.itens)
      } catch (e) {
        if (!ativo) return
        setErro(msgErro(e))
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [sessao.token, apenasNaoLidos])

  function trocarFiltro(apenas: boolean) {
    if (apenas === apenasNaoLidos) return
    setItens(null)
    setErro(null)
    setApenasNaoLidos(apenas)
  }

  async function handleMarcarLido(id: string) {
    setMarcando(id)
    try {
      await marcarAlertaLido(sessao.token, id)
      setItens((atual) => {
        if (!atual) return atual
        if (apenasNaoLidos) {
          return atual.filter((a) => a.id !== id)
        }
        return atual.map((a) =>
          a.id === id ? { ...a, lido_em: new Date().toISOString() } : a,
        )
      })
    } catch (e) {
      setErro(msgErro(e))
    } finally {
      setMarcando(null)
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

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <div className="alertas-toggle">
          <button
            type="button"
            className={apenasNaoLidos ? 'ativo' : ''}
            onClick={() => trocarFiltro(true)}
          >
            Só não lidos
          </button>
          <button
            type="button"
            className={!apenasNaoLidos ? 'ativo' : ''}
            onClick={() => trocarFiltro(false)}
          >
            Todos
          </button>
        </div>

        {erro && <p role="alert">{erro}</p>}

        {!erro && !itens && <p>Carregando...</p>}

        {!erro && itens && itens.length === 0 && (
          <p>
            {apenasNaoLidos
              ? 'Nenhum alerta pendente.'
              : 'Nenhum alerta registrado.'}
          </p>
        )}

        {!erro && itens && itens.length > 0 && (
          <ul className="alertas-lista">
            {itens.map((a) => (
              <li key={a.id} className="alerta-card">
                <div className="alerta-topo">
                  <span className={classeSeveridade(a.severidade)}>
                    {ROTULO_SEVERIDADE[a.severidade] ?? 'Aviso'}
                  </span>
                  <span className="alerta-data">
                    {formatData(a.criado_em)}
                  </span>
                </div>
                <p className="alerta-mensagem">{a.mensagem}</p>
                {a.prazo && (
                  <p className="alerta-prazo">Prazo: {formatData(a.prazo)}</p>
                )}
                {a.lido_em ? (
                  <p className="alerta-lido">
                    Lido em {formatData(a.lido_em)}
                  </p>
                ) : (
                  <button
                    type="button"
                    className="alerta-btn"
                    disabled={marcando === a.id}
                    onClick={() => handleMarcarLido(a.id)}
                  >
                    {marcando === a.id ? 'Marcando...' : 'Marcar como lido'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}