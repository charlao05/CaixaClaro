import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
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
  fato_confirmado: 'Fato confirmado',
  leitura_provavel: 'Leitura provavel',
  duvida_declarada: 'Requer confirmacao',
}

function classeGrau(g: GrauCerteza): string {
  if (g === 'fato_confirmado') return 'opiniao-badge verde'
  if (g === 'leitura_provavel') return 'opiniao-badge azul'
  return 'opiniao-badge ambar'
}

function msgErro(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter
      ? `${e.message} Tente novamente em ${e.retryAfter}s.`
      : e.message
  }
  return 'Erro inesperado.'
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

  const cabecalho = (
    <header>
      <h1>CaixaClaro</h1>
      <div>
        <span>{sessao.user.email}</span>
        <button type="button" onClick={onVoltar}>
          Voltar a lista
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

  if (!opiniao) {
    return (
      <main className="dashboard">
        {cabecalho}
        <p>Carregando...</p>
      </main>
    )
  }

  const g = opiniao.grau_certeza_leitura

  return (
    <main className="dashboard">
      {cabecalho}

      <section>
        <div className="opiniao-topo">
          <h2>Parecer fiscal</h2>
          <span className={classeGrau(g)}>{LABEL_GRAU[g]}</span>
        </div>

        <div className="opiniao-card">
          <Estagio titulo="1. Fato observado" texto={opiniao.fato} />
          <Estagio titulo="2. Interpretacao" texto={opiniao.interpretacao} />
          <Estagio titulo="3. Relacao PF / PJ" texto={opiniao.relacao_pf_pj} />
          <Estagio
            titulo="4. Possivel tratamento tributario"
            texto={opiniao.possivel_tratamento_tributario}
          />
          <Estagio
            titulo="5. Condicoes necessarias"
            texto={opiniao.condicoes_necessarias}
          />
          <Estagio
            titulo="6. O que nao sabemos"
            texto={opiniao.pendencias}
          />
          <Estagio titulo="7. Proximo passo" texto={opiniao.proximo_passo} />

          {opiniao.opcoes_esclarecimento.length > 0 && (
            <div className="opiniao-opcoes">
              <span className="opiniao-estagio-titulo">
                Opcoes de esclarecimento
              </span>
              <ul>
                {opiniao.opcoes_esclarecimento.map((o, i) => (
                  <li key={i}>
                    <strong>{o.label}</strong>
                    <span className="opiniao-opcao-desc">{o.descricao}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>
    </main>
  )
}