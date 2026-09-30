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
  onAlertas: () => void
  onPerfil: () => void
  onTransacoes: () => void
  onContas: () => void
  onAssinatura: () => void
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
  onAlertas,
  onPerfil,
  onTransacoes,
  onContas,
  onAssinatura,
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
        {resumo?.tem_transacoes && (
          <button type="button" onClick={onNovaIngestao}>
            Adicionar lançamento
          </button>
        )}
        <button type="button" onClick={onContas}>
          Contas
        </button>
        <button type="button" onClick={onTransacoes}>
          Lançamentos
        </button>
        <button type="button" onClick={onRevisar}>
          Revisar
          {fila && fila.length > 0 ? ` (${fila.length})` : ''}
        </button>
        <button type="button" onClick={onAlertas}>
          Alertas
          {alertas && alertas.length > 0 ? ` (${alertas.length})` : ''}
        </button>
        <button type="button" onClick={onPerfil}>
          Perfil
        </button>
        <button type="button" onClick={onAssinatura}>
          Assinatura
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

      {!resumo.tem_transacoes && (
        <section className="dashboard-onboarding">
          <h2>Comece pelo seu primeiro extrato</h2>
          <p>
            Conecte uma conta ou cole um extrato para importar suas movimentações.
            Depois, o CaixaClaro organiza os lançamentos e mostra o que precisa da sua revisão.
          </p>
          <button type="button" onClick={onNovaIngestao}>
            Importar extrato
          </button>
        </section>
      )}

      {resumo?.tem_transacoes && (
        <section>
          <h2>Seu dinheiro está sendo acompanhado</h2>
          <p>
            O CaixaClaro já analisou seus lançamentos e mostra o que está
            acontecendo, o que precisa da sua atenção e o que ainda precisa
            ser confirmado.
          </p>
        </section>
      )}

      <section>
        <h2>Seu faturamento em {resumo.ano_referencia}</h2>
        <p>
          <strong>{formatBRL(resumo.faturamento_acumulado)}</strong>
          {' de '}
          {formatBRL(resumo.teto_anual)}
        </p>
        <p>{(resumo.percentual_consumido * 100).toFixed(1)}% do teto anual</p>
        {resumo.proxima_faixa ? (
          <p>
            Próxima faixa: {(resumo.proxima_faixa.percentual * 100).toFixed(0)}% — faltam{' '}
            {formatBRL(resumo.proxima_faixa.falta)}
          </p>
        ) : (
          <p>Todas as faixas foram atingidas.</p>
        )}
      </section>

      <section>
        {fila.length === 0 ? (
          <h2>Nada pendente para revisar no momento.</h2>
        ) : (
          <>
            <h2>
              {fila.length === 1
                ? 'Há 1 item aguardando sua confirmação'
                : `Há ${fila.length} itens aguardando sua confirmação`}
            </h2>
            <p>
              O CaixaClaro identificou movimentações que ainda precisam da sua
              revisão para classificar com segurança.
            </p>
            <button type="button" onClick={onRevisar}>
              Revisar agora
            </button>
          </>
        )}
      </section>

      <section>
        {alertas.length === 0 ? (
          <h2>Nenhum alerta ativo no momento.</h2>
        ) : (
          <>
            <h2>
              {alertas.length === 1
                ? 'Você tem 1 alerta para verificar'
                : `Você tem ${alertas.length} alertas para verificar`}
            </h2>
            <ul>
              {alertas.slice(0, 3).map((a) => (
                <li key={a.id}>
                  <strong>{a.severidade}</strong> — {a.mensagem}
                </li>
              ))}
            </ul>
            {alertas.length > 3 && (
              <p>... e mais {alertas.length - 3}.</p>
            )}
            <button type="button" onClick={onAlertas}>
              Ver todos os alertas
            </button>
          </>
        )}
      </section>
    </main>
  )
}