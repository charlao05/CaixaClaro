import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import { getResumo, type FiscalResumo } from '../services/fiscal'
import { listarAlertas, type Alerta } from '../services/alertas'
import { listarFila, type ItemFila } from '../services/fila'

type Props = {
  sessao: Sessao
  onLogout: () => void
  onNovaIngestao: () => void
  onRevisar: () => void
}

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export default function Dashboard({
  sessao,
  onLogout,
  onNovaIngestao,
  onRevisar,
}: Props) {
  const [resumo, setResumo] = useState<FiscalResumo | null>(null)
  const [alertas, setAlertas] = useState<Alerta[] | null>(null)
  const [fila, setFila] = useState<ItemFila[] | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const [r, a, f] = await Promise.all([
          getResumo(sessao.token),
          listarAlertas(sessao.token, { apenasNaoLidos: true, limite: 20 }),
          listarFila(sessao.token, { limite: 50 }),
        ])
        if (!ativo) return
        setResumo(r)
        setAlertas(a.itens)
        setFila(f.itens)
      } catch (e) {
        if (!ativo) return
        if (e instanceof ApiError) {
          setErro(e.message)
        } else {
          setErro('Erro inesperado.')
        }
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [sessao.token])

  const cabecalho = (
    <header>
      <h1>CaixaClaro</h1>
      <div>
        <span>{sessao.user.email}</span>
        <button type="button" onClick={onNovaIngestao}>
          Nova ingestao
        </button>
        <button type="button" onClick={onRevisar}>
          Revisar
          {fila && fila.length > 0 ? ` (${fila.length})` : ''}
        </button>
        <button type="button" onClick={onLogout}>
          Sair
        </button>
      </div>
    </header>
  )

  if (erro) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p role="alert">{erro}</p>
      </main>
    )
  }

  if (!resumo || !alertas || !fila) {
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
        <h2>Faturamento {resumo.ano_referencia}</h2>
        <p>
          <strong>{formatBRL(resumo.faturamento_acumulado)}</strong>
          {' de '}
          {formatBRL(resumo.teto_anual)}
        </p>
        <p>{(resumo.percentual_consumido * 100).toFixed(1)}% do teto</p>
        {resumo.proxima_faixa ? (
          <p>
            Proxima faixa: {(resumo.proxima_faixa.percentual * 100).toFixed(0)}% — faltam{' '}
            {formatBRL(resumo.proxima_faixa.falta)}
          </p>
        ) : (
          <p>Todas as faixas foram atingidas.</p>
        )}
      </section>

      <section>
        <h2>Alertas nao lidos</h2>
        {alertas.length === 0 ? (
          <p>Nenhum alerta pendente.</p>
        ) : (
          <ul>
            {alertas.map((a) => (
              <li key={a.id}>
                <strong>{a.severidade}</strong> — {a.mensagem}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Fila de revisao</h2>
        {fila.length === 0 ? (
          <p>Nada para revisar.</p>
        ) : (
          <p>
            {fila.length}{' '}
            {fila.length === 1 ? 'item pendente' : 'itens pendentes'}
          </p>
        )}
      </section>
    </main>
  )
}