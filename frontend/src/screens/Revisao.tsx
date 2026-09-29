import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import { listarFila, confirmar, type ItemFila } from '../services/fila'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

type OpcaoRapida = {
  label: string
  descricao: string
  categoria: string
}

const OPCOES_RAPIDAS: OpcaoRapida[] = [
  {
    label: 'Foi pagamento por trabalho ou serviço',
    descricao: 'Renda profissional — entra no faturamento',
    categoria: 'receita_servico',
  },
  {
    label: 'Foi venda de produto',
    descricao: 'Comércio — entra no faturamento',
    categoria: 'receita_venda',
  },
  {
    label: 'Foi transferência entre minhas contas',
    descricao: 'Mesma titularidade — isento',
    categoria: 'transferencia_propria',
  },
  {
    label: 'Foi empréstimo ou devolução',
    descricao: 'Não é renda',
    categoria: 'emprestimo',
  },
]

const CATEGORIAS_COMPLETAS: { id: string; label: string }[] = [
  { id: 'receita_servico', label: 'Trabalho / Prestação de Serviço' },
  { id: 'receita_venda', label: 'Vendas de Produtos / Comércio' },
  { id: 'salario', label: 'Salário Formal / Aposentadoria' },
  { id: 'imposto_das', label: 'Impostos e Tributos (DAS/IRPF/DARF)' },
  { id: 'taxas_tarifas', label: 'Taxas Bancárias & Maquininha' },
  { id: 'custo_operacional', label: 'Gastos da Atividade / Trabalho' },
  { id: 'transferencia_propria', label: 'Transferência Entre Contas Próprias' },
  { id: 'pessoal_prolabore', label: 'Retirada da Empresa / Pró-Labore' },
  { id: 'reembolso', label: 'Devolução / Reembolso' },
  { id: 'emprestimo', label: 'Empréstimo (peguei ou emprestei)' },
  { id: 'outros', label: 'Aguardando Confirmação' },
]

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
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

export default function Revisao({ sessao, onVoltar }: Props) {
  const [itens, setItens] = useState<ItemFila[] | null>(null)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)
  const [processando, setProcessando] = useState(false)
  const [erroConfirmar, setErroConfirmar] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [categoriaManual, setCategoriaManual] = useState('')

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const r = await listarFila(sessao.token, { limite: 100 })
        if (!ativo) return
        setItens(r.itens)
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
    if (!feedback) return
    const id = setTimeout(() => setFeedback(null), 2500)
    return () => clearTimeout(id)
  }, [feedback])

  async function handleConfirmar(categoria: string) {
    if (!itens || itens.length === 0) return
    const atual = itens[0]
    setProcessando(true)
    setErroConfirmar(null)
    try {
      const r = await confirmar(sessao.token, atual.id, categoria)
      setItens(itens.slice(1))
      setCategoriaManual('')
      const partes: string[] = []
      if (r.categoria_mudou) {
        partes.push(`Categoria: ${r.categoria_antiga} -> ${r.categoria_nova}`)
      }
      const delta = parseFloat(r.delta_faturamento)
      if (delta > 0) {
        partes.push(`Faturamento +${formatBRL(r.delta_faturamento)}`)
      } else if (delta < 0) {
        partes.push(`Faturamento ${formatBRL(r.delta_faturamento)}`)
      } else {
        partes.push('Sem impacto no faturamento')
      }
      setFeedback(partes.join(' • '))
    } catch (e) {
      setErroConfirmar(msgErro(e))
    } finally {
      setProcessando(false)
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

  if (!itens) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  if (itens.length === 0) {
    return (
      <main className="dashboard">
        {cabecalho}
        <section>
          <h2>Tudo verificado e seguro</h2>
          <p>Nenhuma movimentacao pendente de confirmacao no momento.</p>
        </section>
      </main>
    )
  }

  const atual = itens[0]
  const total = itens.length

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <p className="revisao-progresso">
          <strong>Pendencia 1 de {total}</strong>
        </p>

        <div className="revisao-card">
          <h2 className="revisao-valor">{formatBRL(atual.valor)}</h2>
          <p className="revisao-descricao">{atual.descricao_bruta}</p>
          <p className="revisao-data">{formatData(atual.data)}</p>

          {atual.motivo && (
            <p className="revisao-motivo">
              <strong>Por que o CaixaClaro perguntou?</strong> {atual.motivo}
            </p>
          )}

          {feedback && (
            <p role="status" className="revisao-feedback">
              {feedback}
            </p>
          )}

          {erroConfirmar && <p role="alert">{erroConfirmar}</p>}

          <p className="revisao-pergunta">
            <strong>O que foi este valor?</strong>
          </p>

          <div className="revisao-opcoes">
            {OPCOES_RAPIDAS.map((o) => (
              <button
                key={o.categoria}
                type="button"
                onClick={() => handleConfirmar(o.categoria)}
                disabled={processando}
              >
                <span className="revisao-opcao-label">{o.label}</span>
                <span className="revisao-opcao-desc">{o.descricao}</span>
              </button>
            ))}
          </div>

          <div className="revisao-manual">
            <label>
              Outra categoria
              <select
                value={categoriaManual}
                onChange={(e) => setCategoriaManual(e.target.value)}
                disabled={processando}
              >
                <option value="">Escolha...</option>
                {CATEGORIAS_COMPLETAS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => handleConfirmar(categoriaManual)}
              disabled={processando || categoriaManual === ''}
            >
              Confirmar categoria
            </button>
          </div>
        </div>
      </section>
    </main>
  )
}