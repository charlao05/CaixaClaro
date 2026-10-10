import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  listarFila,
  confirmar,
  type ItemFila,
  type OpcaoResposta,
} from '../services/fila'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

function formatBRL(s: string): string {
  const n = Math.abs(parseFloat(s))
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
  return 'Algo deu errado. Tente de novo em instantes.'
}

function saiu(valor: string): boolean {
  return parseFloat(valor) < 0
}

function mesmaPergunta(a: ItemFila, b: ItemFila): boolean {
  return (
    a.descricao_bruta.trim().toLowerCase() === b.descricao_bruta.trim().toLowerCase() &&
    saiu(a.valor) === saiu(b.valor)
  )
}

export default function Revisao({ sessao, onVoltar }: Props) {
  const [itens, setItens] = useState<ItemFila[] | null>(null)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)
  const [processando, setProcessando] = useState(false)
  const [erroConfirmar, setErroConfirmar] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [lembrar, setLembrar] = useState(false)
  const [respondidos, setRespondidos] = useState(0)

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
    const id = setTimeout(() => setFeedback(null), 7000)
    return () => clearTimeout(id)
  }, [feedback])

  async function handleResponder(opcao: OpcaoResposta) {
    if (!itens || itens.length === 0) return
    const atual = itens[0]
    setProcessando(true)
    setErroConfirmar(null)
    try {
      const r = await confirmar(sessao.token, atual.id, {
        categoria: opcao.categoria,
        proposito: opcao.proposito,
        lembrar,
      })
      const resolvidos = new Set<string>([atual.id, ...r.ids_aplicados])
      setItens(itens.filter((i) => !resolvidos.has(i.id)))
      setRespondidos((n) => n + resolvidos.size)
      setFeedback(r.mensagem)
    } catch (e) {
      setErroConfirmar(msgErro(e))
    } finally {
      setProcessando(false)
    }
  }

  function handlePular() {
    if (!itens || itens.length < 2) return
    setErroConfirmar(null)
    setFeedback('Sem problema. Este lançamento continua guardado, esperando.')
    setItens([...itens.slice(1), itens[0]])
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
          <h2>Tudo respondido</h2>
          {feedback && (
            <p role="status" className="revisao-feedback">
              {feedback}
            </p>
          )}
          <p>Nenhum lançamento esperando a sua resposta.</p>
          <button type="button" onClick={onVoltar}>
            Ver o painel
          </button>
        </section>
      </main>
    )
  }

  const atual = itens[0]
  const total = itens.length
  const iguais = itens.filter((i) => i.id !== atual.id && mesmaPergunta(i, atual)).length
  const foiSaida = saiu(atual.valor)

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <p className="revisao-progresso">
          <strong>
            {total === 1 ? 'Falta 1 resposta' : `Faltam ${total} respostas`}
          </strong>
          {respondidos > 0 ? ` · ${respondidos} já resolvidos agora` : ''}
        </p>

        {feedback && (
          <p role="status" className="revisao-feedback">
            {feedback}
          </p>
        )}

        <div className="revisao-card">
          <h2 className="revisao-valor">{formatBRL(atual.valor)}</h2>
          <p className="revisao-pergunta">
            {foiSaida
              ? `Saíram ${formatBRL(atual.valor)} da sua conta em ${formatData(atual.data)}.`
              : `Entraram ${formatBRL(atual.valor)} na sua conta em ${formatData(atual.data)}.`}
          </p>
          <p className="revisao-descricao">
            No extrato aparece assim: <strong>{atual.descricao_bruta}</strong>
          </p>

          {atual.motivo && (
            <p className="revisao-motivo">
              <strong>Por que o CaixaClaro está perguntando?</strong> {atual.motivo}
            </p>
          )}

          {erroConfirmar && <p role="alert">{erroConfirmar}</p>}

          <p className="revisao-pergunta">
            <strong>O que foi?</strong>
          </p>

          <div className="revisao-opcoes">
            {atual.opcoes.map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => handleResponder(o)}
                disabled={processando}
              >
                <span className="revisao-opcao-label">{o.label}</span>
                <span className="revisao-opcao-desc">{o.descricao}</span>
              </button>
            ))}
          </div>

          <div className="revisao-manual">
            <label className="revisao-lembrar">
              <input
                type="checkbox"
                checked={lembrar}
                onChange={(e) => setLembrar(e.target.checked)}
                disabled={processando}
              />
              {iguais > 0
                ? iguais === 1
                  ? 'Usar a mesma resposta para o outro lançamento igual e para os próximos'
                  : `Usar a mesma resposta para os outros ${iguais} lançamentos iguais e para os próximos`
                : 'Lembrar desta resposta quando aparecer outro lançamento igual'}
            </label>
            <button
              type="button"
              onClick={handlePular}
              disabled={processando || total < 2}
            >
              Não sei agora — pular
            </button>
          </div>
          <p className="assinatura-nota">
            Tudo bem não saber. Nada é contado como renda enquanto você não
            disser o que foi.
          </p>
        </div>
      </section>
    </main>
  )
}
