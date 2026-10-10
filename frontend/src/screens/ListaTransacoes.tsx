import { useEffect, useState } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  listarTransacoes,
  type TransacaoCompleta,
} from '../services/transacoes'

type Props = {
  sessao: Sessao
  onVoltar: () => void
  onSelecionar: (txId: string) => void
}

const LIMITE = 50

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

export default function ListaTransacoes({
  sessao,
  onVoltar,
  onSelecionar,
}: Props) {
  const [itens, setItens] = useState<TransacaoCompleta[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      setCarregando(true)
      try {
        const r = await listarTransacoes(sessao.token, { limite: LIMITE })
        if (!ativo) return
        setItens(r.itens)
        setCursor(r.next_cursor)
        setHasMore(r.has_more)
      } catch (e) {
        if (!ativo) return
        setErro(msgErro(e))
      } finally {
        if (ativo) setCarregando(false)
      }
    }
    carregar()
    return () => {
      ativo = false
    }
  }, [sessao.token])

  async function handleCarregarMais() {
    if (!cursor || !itens) return
    setCarregando(true)
    setErro(null)
    try {
      const r = await listarTransacoes(sessao.token, {
        limite: LIMITE,
        cursor,
      })
      setItens([...itens, ...r.itens])
      setCursor(r.next_cursor)
      setHasMore(r.has_more)
    } catch (e) {
      setErro(msgErro(e))
    } finally {
      setCarregando(false)
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
        <h2>Lançamentos</h2>

        {erro && <p role="alert">{erro}</p>}

        {!erro && !itens && <p>Carregando...</p>}

        {!erro && itens && itens.length === 0 && (
          <p>Nenhum lançamento registrado.</p>
        )}

        {!erro && itens && itens.length > 0 && (
          <>
            <ul className="tx-lista">
              {itens.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    className="tx-item"
                    onClick={() => onSelecionar(t.id)}
                  >
                    <span className="tx-data">{formatData(t.data)}</span>
                    <span className="tx-desc">{t.descricao_bruta}</span>
                    <span className="tx-valor">{formatBRL(t.valor)}</span>
                    <span className="tx-cat">
                      {t.rotulo}
                      {t.needs_review && (
                        <span className="tx-pend"> · falta a sua resposta</span>
                      )}
                      {t.confirmada && <span> · confirmado por você</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            {hasMore && (
              <button
                type="button"
                className="tx-mais"
                onClick={handleCarregarMais}
                disabled={carregando}
              >
                {carregando ? 'Carregando...' : 'Carregar mais'}
              </button>
            )}
          </>
        )}
      </section>
    </main>
  )
}