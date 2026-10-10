import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import { corrigir, type OpcaoResposta } from '../services/fila'
import {
  getOpiniao,
  type GrauCerteza,
  type Opiniao as DadosOpiniao,
} from '../services/tax_opinion'

type Props = {
  sessao: Sessao
  txId: string
  onVoltar: () => void
}

const LABEL_GRAU: Record<GrauCerteza, string> = {
  fato_confirmado: 'Confirmado por você',
  leitura_provavel: 'Leitura do CaixaClaro — você não confirmou',
  duvida_declarada: 'Falta a sua resposta',
}

function classeGrau(g: GrauCerteza): string {
  if (g === 'fato_confirmado') return 'opiniao-badge verde'
  if (g === 'leitura_provavel') return 'opiniao-badge azul'
  return 'opiniao-badge ambar'
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

function Estagio({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <div className="opiniao-estagio">
      <span className="opiniao-estagio-titulo">{titulo}</span>
      <p className="opiniao-estagio-texto">{texto}</p>
    </div>
  )
}

export default function Opiniao({ sessao, txId, onVoltar }: Props) {
  const [opiniao, setOpiniao] = useState<DadosOpiniao | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [escolhendo, setEscolhendo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const o = await getOpiniao(sessao.token, txId)
        if (!ativo) return
        setOpiniao(o)
      } catch (e) {
        if (!ativo) return
        setErro(msgErro(e))
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [sessao.token, txId])

  async function handleEscolher(o: OpcaoResposta) {
    setSalvando(true)
    setErro(null)
    try {
      const r = await corrigir(sessao.token, txId, {
        categoria: o.categoria,
        proposito: o.proposito,
      })
      setAviso(r.mensagem)
      setEscolhendo(false)
      setOpiniao(await getOpiniao(sessao.token, txId))
    } catch (e) {
      setErro(msgErro(e))
    } finally {
      setSalvando(false)
    }
  }

  const cabecalho = (
    <header>
      <h1>CaixaClaro</h1>
      <div>
        <span>{sessao.user.email}</span>
        <button type="button" onClick={onVoltar}>
          Voltar à lista
        </button>
      </div>
    </header>
  )

  if (erro && !opiniao) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p role="alert">{erro}</p>
      </main>
    )
  }

  if (!opiniao) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  const g = opiniao.grau_certeza_leitura
  const faltaResposta = g === 'duvida_declarada'
  const mostrarOpcoes = escolhendo || faltaResposta

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <div className="opiniao-topo">
          <h2>Entenda este lançamento</h2>
          <span className={classeGrau(g)}>{LABEL_GRAU[g]}</span>
        </div>

        <p className="revisao-descricao">
          {formatData(opiniao.data)} · <strong>{formatBRL(opiniao.valor)}</strong> ·{' '}
          {opiniao.descricao}
        </p>
        <p>
          <strong>{opiniao.rotulo}</strong>
        </p>

        {aviso && (
          <p role="status" className="revisao-feedback">
            {aviso}
          </p>
        )}
        {erro && <p role="alert">{erro}</p>}

        <div className="opiniao-card">
          <Estagio titulo="O que aconteceu" texto={opiniao.fato} />
          <Estagio titulo="O que isso significa" texto={opiniao.interpretacao} />
          <Estagio
            titulo="É da vida pessoal ou do trabalho?"
            texto={opiniao.relacao_pf_pj}
          />
          <Estagio
            titulo="Tem a ver com imposto?"
            texto={opiniao.possivel_tratamento_tributario}
          />
          <Estagio titulo="Isso vale se…" texto={opiniao.condicoes_necessarias} />
          <Estagio
            titulo="O que o CaixaClaro não sabe"
            texto={opiniao.pendencias}
          />
          <Estagio
            titulo="O que dá para fazer agora"
            texto={opiniao.proximo_passo}
          />
        </div>

        {mostrarOpcoes ? (
          <div className="revisao-card">
            <p className="revisao-pergunta">
              <strong>
                {faltaResposta ? 'O que foi este lançamento?' : 'O que foi, de verdade?'}
              </strong>
            </p>
            <div className="revisao-opcoes">
              {opiniao.opcoes_correcao.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => handleEscolher(o)}
                  disabled={salvando}
                >
                  <span className="revisao-opcao-label">{o.label}</span>
                  <span className="revisao-opcao-desc">{o.descricao}</span>
                </button>
              ))}
            </div>
            {!faltaResposta && (
              <button
                type="button"
                onClick={() => setEscolhendo(false)}
                disabled={salvando}
              >
                Deixar como está
              </button>
            )}
          </div>
        ) : (
          <button type="button" onClick={() => setEscolhendo(true)}>
            Não foi isso? Corrigir
          </button>
        )}

        <p className="assinatura-nota">
          Esta explicação ajuda você a se organizar e a conversar com um
          contador. Não é apuração de imposto nem substitui um profissional.
        </p>
      </section>
    </main>
  )
}
