import { api } from './api'

// ---------- Produtos / Servicos ----------

export type TipoProduto = 'produto' | 'servico'

export type Produto = {
  id: string
  tipo: TipoProduto
  nome: string
  unidade_medida: string
  custo_atual: string | null
  preco_atual: string | null
  controla_estoque: boolean
  ativo: boolean
  criado_em: string
  atualizado_em: string
}

export type ListarProdutosResponse = {
  itens: Produto[]
}

export type ProdutoIn = {
  tipo: TipoProduto
  nome: string
  unidade_medida?: string
  custo_atual?: string | null
  preco_atual?: string | null
  controla_estoque?: boolean
}

export type ProdutoPatch = {
  nome?: string
  unidade_medida?: string
  custo_atual?: string | null
  preco_atual?: string | null
  controla_estoque?: boolean
  ativo?: boolean
}

// ---------- Precificacao ----------

export type CenarioIn = {
  nome: string
  preco: string
  custo_variavel_unitario: string
  custos_fixos_periodo?: string | null
  volume_hipotese?: string | null
}

export type EstadoCalculo = 'calculo' | 'limitacao'

export type Calculo = {
  nome: string
  formula: string
  variaveis: Record<string, string>
  resultado: string | null
  unidade: string
  estado: EstadoCalculo
  limitacao: string | null
}

export type CenarioCalculado = {
  nome: string
  hipoteses: Record<string, string>
  calculos: Calculo[]
  limitacoes: string[]
}

export type PrecificarIn = {
  cenarios: CenarioIn[]
  salvar?: boolean
  product_id?: string
}

export type PrecificacaoResponse = {
  cenarios: CenarioCalculado[]
  comparacao: string | null
}

// ---------- Funcoes ----------

export function listarProdutos(
  token: string,
  opts: { apenasAtivos?: boolean } = {},
): Promise<ListarProdutosResponse> {
  const apenasAtivos = opts.apenasAtivos ?? true
  const params = new URLSearchParams()
  params.set('apenas_ativos', String(apenasAtivos))
  return api<ListarProdutosResponse>(`/produtos?${params.toString()}`, { token })
}

export function obterProduto(token: string, produtoId: string): Promise<Produto> {
  return api<Produto>(`/produtos/${produtoId}`, { token })
}

export function criarProduto(token: string, dados: ProdutoIn): Promise<Produto> {
  return api<Produto>('/produtos', {
    method: 'POST',
    body: dados,
    token,
  })
}

export function atualizarProduto(
  token: string,
  produtoId: string,
  campos: ProdutoPatch,
): Promise<Produto> {
  return api<Produto>(`/produtos/${produtoId}`, {
    method: 'PATCH',
    body: campos,
    token,
  })
}

export function calcularPrecificacao(
  token: string,
  dados: PrecificarIn,
): Promise<PrecificacaoResponse> {
  return api<PrecificacaoResponse>('/precificacao/calcular', {
    method: 'POST',
    body: dados,
    token,
  })
}

export function removerProduto(token: string, produtoId: string): Promise<void> {
  return api<void>(`/produtos/${produtoId}`, {
    method: 'DELETE',
    token,
  })
}