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
  onNegocio: () => void
}

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const MESES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]

function nomeMes(ym: string | null): string {
  if (!ym) return ''
  const [ano, mes] = ym.split('-')
  const nome = MESES[parseInt(mes, 10) - 1]
  return nome ? `${nome} de ${ano}` : ym
}

const SEVERIDADE: Record<string, string> = {
  informativo: 'Aviso',
  atencao: 'Atenção',
  critico: 'Importante',
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
  onNegocio,
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
        if (e instanceof ApiError && e.estado) {
          // E2: bloqueio de acesso sinalizado pelo backend
          onAssinatura()
          return
        }
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
        <button type="button" onClick={onNegocio}>
          Meu Negócio
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

  const organizados = resumo.total_lancamentos - resumo.pendentes_revisao
  const temMes = resumo.mes_referencia && resumo.entradas_mes && resumo.saidas_mes

  return (
    <main className="dashboard">
      {cabecalho}

      {!resumo.tem_transacoes && (
        <section className="dashboard-onboarding">
          <h2>Comece do jeito mais fácil para você</h2>
          <p>
            Você não precisa entender de imposto nem de contabilidade. Traga
            as suas movimentações e o CaixaClaro explica cada uma, em
            português simples. Quando ele não souber, ele pergunta.
          </p>
          <div className="painel-acoes">
            <button type="button" onClick={onNovaIngestao}>
              Colar ou enviar um extrato
            </button>
            <button type="button" onClick={onContas}>
              Conectar a conta do banco
            </button>
            <button type="button" onClick={onNovaIngestao}>
              Anotar um recebimento ou gasto
            </button>
          </div>
        </section>
      )}

      {resumo.tem_transacoes && (
        <section>
          <h2>O que você já trouxe</h2>
          <div className="painel-numeros">
            <div>
              <strong>{organizados}</strong>
              <small>{organizados === 1 ? 'lançamento organizado' : 'lançamentos organizados'}</small>
            </div>
            <div>
              <strong>{resumo.pendentes_revisao}</strong>
              <small>esperando a sua resposta</small>
            </div>
            <div>
              <strong>{alertas.length}</strong>
              <small>{alertas.length === 1 ? 'aviso novo' : 'avisos novos'}</small>
            </div>
          </div>
          {resumo.pendentes_revisao > 0 && (
            <button type="button" onClick={onRevisar}>
              Responder agora
            </button>
          )}
        </section>
      )}

      {temMes && (
        <section>
          <h2>Em {nomeMes(resumo.mes_referencia)}</h2>
          <p>
            Entraram <strong>{formatBRL(resumo.entradas_mes ?? '0')}</strong> e
            saíram <strong>{formatBRL(resumo.saidas_mes ?? '0')}</strong>.
          </p>
          <p className="assinatura-nota">
            É a soma de tudo o que você trouxe neste mês. Dinheiro que só
            passou entre contas suas também entra nessa soma.
          </p>
        </section>
      )}

      {resumo.regime === 'MEI' && resumo.teto_anual !== null && (
        <section>
          <h2>Seu faturamento como MEI em {resumo.ano_referencia}</h2>
          <p>
            <strong>{formatBRL(resumo.faturamento_acumulado)}</strong>
            {' de '}
            {formatBRL(resumo.teto_anual)}
          </p>
          {resumo.percentual_consumido !== null && (
            <p>{(resumo.percentual_consumido * 100).toFixed(1)}% do limite anual do MEI</p>
          )}
          {resumo.proxima_faixa && (
            <p>
              Faltam {formatBRL(resumo.proxima_faixa.falta)} para chegar a{' '}
              {(resumo.proxima_faixa.percentual * 100).toFixed(0)}% do limite.
            </p>
          )}
          <p className="assinatura-nota">
            {resumo.limite_proporcional
              ? 'Seu MEI abriu neste ano, então o limite é proporcional aos meses de atividade. '
              : ''}
            Entra aqui o que você confirmou como trabalho ou venda.
            {resumo.pendentes_revisao > 0
              ? ' Ainda há lançamentos sem resposta: este número pode mudar.'
              : ''}
          </p>
        </section>
      )}

      {resumo.regime !== 'MEI' && (
        <section>
          <h2>
            {resumo.regime === 'SIMPLES'
              ? `Receitas do seu negócio em ${resumo.ano_referencia}`
              : `O que você recebeu por trabalho em ${resumo.ano_referencia}`}
          </h2>
          <p>
            <strong>{formatBRL(resumo.faturamento_acumulado)}</strong>
          </p>
          <p className="assinatura-nota">
            É a soma das entradas que você confirmou como trabalho ou venda.
            Não é cálculo de imposto.
            {resumo.pendentes_revisao > 0
              ? ' Ainda há lançamentos sem resposta: este número pode mudar.'
              : ''}
          </p>
        </section>
      )}

      <section>
        {alertas.length === 0 ? (
          <h2>Nenhum aviso novo.</h2>
        ) : (
          <>
            <h2>
              {alertas.length === 1
                ? 'Você tem 1 aviso para ver'
                : `Você tem ${alertas.length} avisos para ver`}
            </h2>
            <ul>
              {alertas.slice(0, 3).map((a) => (
                <li key={a.id}>
                  <strong>{SEVERIDADE[a.severidade] ?? 'Aviso'}</strong> — {a.mensagem}
                </li>
              ))}
            </ul>
            {alertas.length > 3 && <p>... e mais {alertas.length - 3}.</p>}
            <button type="button" onClick={onAlertas}>
              Ver todos os avisos
            </button>
          </>
        )}
      </section>
    </main>
  )
}
