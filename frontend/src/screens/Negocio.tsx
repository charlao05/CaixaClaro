import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  listarProdutos,
  criarProduto,
  atualizarProduto,
  removerProduto,
  calcularPrecificacao,
  type Produto,
  type TipoProduto,
  type Calculo,
  type CenarioCalculado,
} from '../services/produtos'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

type EstadoPrecificacao = {
  cenario: CenarioCalculado
  comparacao: string | null
}

const LABELS_HUMANOS: Record<string, string> = {
  diferenca_preco_custo: 'Cada venda te deixa isso no bolso',
  margem_contribuicao_unitaria_reais: 'O que sobra de cada venda',
  margem_contribuicao_unitaria_percentual:
    'Quanto isso representa do preço que você cobra',
  ponto_equilibrio_unidades: 'Quantas vendas por mês só pra empatar',
  ponto_equilibrio_receita: 'Faturamento necessário por mês pra empatar',
}

function labelCalculo(nome: string): string {
  return LABELS_HUMANOS[nome] ?? nome
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

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function normalizarDecimalBR(input: string): string {
  const t = input.trim()
  if (t === '') return ''
  if (t.includes(',') && t.includes('.')) {
    return t.replace(/\./g, '').replace(',', '.')
  }
  if (t.includes(',')) {
    return t.replace(',', '.')
  }
  return t
}

function labelTipo(t: TipoProduto): string {
  return t === 'produto' ? 'Produto' : 'Serviço'
}

function formatarResultado(c: Calculo): string {
  if (c.estado === 'limitacao') return c.limitacao ?? 'Não calculado.'
  if (c.resultado === null) return '-'
  if (c.unidade === 'R$' || c.unidade === 'R$/unidade') {
    return formatBRL(c.resultado)
  }
  const bruto = c.resultado.replace('.', ',')
  if (c.unidade === '%') return `${bruto}%`
  return `${bruto} ${c.unidade}`
}

export default function Negocio({ sessao, onVoltar }: Props) {
  const [produtos, setProdutos] = useState<Produto[] | null>(null)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)

  const [editandoId, setEditandoId] = useState<string | null>(null)
  const [tipo, setTipo] = useState<TipoProduto>('produto')
  const [nome, setNome] = useState('')
  const [unidade, setUnidade] = useState('un')
  const [custo, setCusto] = useState('')
  const [preco, setPreco] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [erroForm, setErroForm] = useState<string | null>(null)

  const [calcPreco, setCalcPreco] = useState('')
  const [calcCusto, setCalcCusto] = useState('')
  const [calcFixos, setCalcFixos] = useState('')
  const [calculando, setCalculando] = useState(false)
  const [erroCalc, setErroCalc] = useState<string | null>(null)
  const [resultado, setResultado] = useState<EstadoPrecificacao | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const r = await listarProdutos(sessao.token, { apenasAtivos: true })
        if (!ativo) return
        setProdutos(r.itens)
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

  function limparForm() {
    setEditandoId(null)
    setTipo('produto')
    setNome('')
    setUnidade('un')
    setCusto('')
    setPreco('')
    setErroForm(null)
  }

  function handleEditar(p: Produto) {
    setEditandoId(p.id)
    setTipo(p.tipo)
    setNome(p.nome)
    setUnidade(p.unidade_medida)
    setCusto(p.custo_atual ?? '')
    setPreco(p.preco_atual ?? '')
    setErroForm(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSalvar(e: FormEvent) {
    e.preventDefault()
    setErroForm(null)
    if (!nome.trim()) {
      setErroForm('Informe o nome.')
      return
    }

    if (!editandoId && produtos) {
      const alvo = nome.trim().toLowerCase()
      const existente = produtos.find((p) => p.nome.toLowerCase() === alvo)
      if (existente) {
        const ok = window.confirm(
          `Você já tem "${existente.nome}" cadastrado. Criar outro com o mesmo nome?`,
        )
        if (!ok) return
      }
    }

    setSalvando(true)
    try {
      const dados = {
        tipo,
        nome: nome.trim(),
        unidade_medida: unidade || 'un',
        custo_atual: custo.trim() === '' ? null : normalizarDecimalBR(custo),
        preco_atual: preco.trim() === '' ? null : normalizarDecimalBR(preco),
      }

      if (editandoId) {
        const atualizado = await atualizarProduto(sessao.token, editandoId, {
          nome: dados.nome,
          unidade_medida: dados.unidade_medida,
          custo_atual: dados.custo_atual,
          preco_atual: dados.preco_atual,
        })
        setProdutos((atual) =>
          atual ? atual.map((p) => (p.id === editandoId ? atualizado : p)) : null,
        )
      } else {
        const novo = await criarProduto(sessao.token, dados)
        setProdutos((atual) => (atual ? [...atual, novo] : [novo]))
      }
      limparForm()
    } catch (err) {
      setErroForm(msgErro(err))
    } finally {
      setSalvando(false)
    }
  }

  async function handleRemover(p: Produto) {
    const ok = window.confirm(
      `Remover "${p.nome}"? Ele sai da lista, mas o histórico é preservado.`,
    )
    if (!ok) return
    setErroForm(null)
    try {
      await removerProduto(sessao.token, p.id)
      setProdutos((atual) => (atual ? atual.filter((x) => x.id !== p.id) : null))
      if (editandoId === p.id) limparForm()
    } catch (err) {
      setErroForm(msgErro(err))
    }
  }

  function preencherCalculoDe(p: Produto) {
    setCalcPreco(p.preco_atual ?? '')
    setCalcCusto(p.custo_atual ?? '')
    setCalcFixos('')
    setResultado(null)
    setErroCalc(null)
  }

  async function handleCalcular(e: FormEvent) {
    e.preventDefault()
    setErroCalc(null)
    setResultado(null)
    if (!calcPreco.trim() || !calcCusto.trim()) {
      setErroCalc('Preencha quanto você vende e quanto gasta por unidade.')
      return
    }
    setCalculando(true)
    try {
      const resp = await calcularPrecificacao(sessao.token, {
        cenarios: [
          {
            nome: 'Preço informado',
            preco: normalizarDecimalBR(calcPreco),
            custo_variavel_unitario: normalizarDecimalBR(calcCusto),
            custos_fixos_periodo:
              calcFixos.trim() === '' ? null : normalizarDecimalBR(calcFixos),
          },
        ],
      })
      setResultado({ cenario: resp.cenarios[0], comparacao: resp.comparacao })
    } catch (err) {
      setErroCalc(msgErro(err))
    } finally {
      setCalculando(false)
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

  if (!produtos) {
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
        <h2>Meu Negócio</h2>
        <p className="assinatura-nota">
          Cadastre o que você vende e descubra quanto sobra em cada venda.
          Os cálculos usam apenas os valores que você informa.
        </p>

        {produtos.length === 0 ? (
          <p>Nenhum produto ou serviço cadastrado ainda.</p>
        ) : (
          <ul className="contas-lista">
            {produtos.map((p) => (
              <li key={p.id} className="conta-item">
                <div className="conta-info">
                  <strong>{p.nome}</strong>
                  <span className="conta-meta">
                    {labelTipo(p.tipo)} - {p.unidade_medida}
                    {p.preco_atual ? ` - Preço: ${formatBRL(p.preco_atual)}` : ''}
                    {p.custo_atual ? ` - Custo: ${formatBRL(p.custo_atual)}` : ''}
                  </span>
                </div>
                <div className="conta-acoes">
                  <button type="button" onClick={() => preencherCalculoDe(p)}>
                    Calcular
                  </button>
                  <button type="button" onClick={() => handleEditar(p)}>
                    Editar
                  </button>
                  <button type="button" onClick={() => handleRemover(p)}>
                    Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3>{editandoId ? 'Editar produto ou serviço' : 'Novo produto ou serviço'}</h3>
        <form onSubmit={handleSalvar}>
          <label>
            Tipo
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TipoProduto)}
              disabled={editandoId !== null}
            >
              <option value="produto">Produto</option>
              <option value="servico">Serviço</option>
            </select>
          </label>
          <label>
            Nome
            <input
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={200}
              placeholder="ex: Camiseta, Corte de cabelo, Consultoria"
            />
          </label>
          <label>
            Unidade
            <input
              type="text"
              value={unidade}
              onChange={(e) => setUnidade(e.target.value)}
              maxLength={20}
              placeholder="ex: un, kg, hora"
            />
          </label>
          <label>
            Quanto você gasta pra fazer cada um? (R$)
            <input
              type="text"
              inputMode="decimal"
              value={custo}
              onChange={(e) => setCusto(e.target.value)}
              placeholder="ex: 18,00"
            />
          </label>
          <label>
            Por quanto você vende cada um? (R$)
            <input
              type="text"
              inputMode="decimal"
              value={preco}
              onChange={(e) => setPreco(e.target.value)}
              placeholder="ex: 49,90"
            />
          </label>
          {erroForm && <p role="alert">{erroForm}</p>}
          <div className="conta-acoes">
            <button type="submit" disabled={salvando}>
              {salvando
                ? 'Salvando...'
                : editandoId
                  ? 'Salvar alterações'
                  : 'Cadastrar'}
            </button>
            {editandoId && (
              <button type="button" onClick={limparForm}>
                Cancelar
              </button>
            )}
          </div>
        </form>
      </section>

      <section>
        <h3>Calcular quanto sobra em cada venda</h3>
        <p className="assinatura-nota">
          Preencha os valores abaixo pra ver a diferença entre preço e custo,
          a margem de contribuição e o ponto de equilíbrio.
        </p>
        <form onSubmit={handleCalcular}>
          <label>
            Por quanto você vende cada um? (R$)
            <input
              type="text"
              inputMode="decimal"
              value={calcPreco}
              onChange={(e) => setCalcPreco(e.target.value)}
              placeholder="ex: 49,90"
            />
          </label>
          <label>
            Quanto você gasta pra fazer cada um? (R$)
            <input
              type="text"
              inputMode="decimal"
              value={calcCusto}
              onChange={(e) => setCalcCusto(e.target.value)}
              placeholder="ex: 18,00"
            />
          </label>
          <label>
            Por mês, quanto você paga de coisas fixas? (R$, opcional)
            <input
              type="text"
              inputMode="decimal"
              value={calcFixos}
              onChange={(e) => setCalcFixos(e.target.value)}
              placeholder="ex: 2000,00"
            />
          </label>
          {erroCalc && <p role="alert">{erroCalc}</p>}
          <button type="submit" disabled={calculando}>
            {calculando ? 'Calculando...' : 'Calcular'}
          </button>
        </form>
      </section>

      {resultado && (
        <section>
          <h3>O que a gente encontrou</h3>
          <ul className="contas-lista">
            {resultado.cenario.calculos.map((c) => (
              <li key={c.nome} className="conta-item">
                <div className="conta-info">
                  <strong>{labelCalculo(c.nome)}</strong>
                  <span className="conta-meta">
                    {c.estado === 'calculo'
                      ? formatarResultado(c)
                      : c.limitacao ?? 'Não calculado.'}
                  </span>
                  <span className="conta-meta">
                    <small>Fórmula: {c.formula}</small>
                  </span>
                </div>
              </li>
            ))}
          </ul>
          {resultado.cenario.limitacoes.length > 0 && (
            <div className="assinatura-nota">
              <strong>O que este cálculo não considera</strong>
              <ul>
                {resultado.cenario.limitacoes.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </main>
  )
}