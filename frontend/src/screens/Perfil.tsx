import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import type { Regime } from '../services/auth'
import { getPerfil, atualizarPerfil, type Perfil as DadosPerfil } from '../services/perfil'

type Props = {
  sessao: Sessao
  onVoltar: () => void
  onAtualizarUsuario: (nome: string | null, regime: Regime) => void
}

const REGIMES: { id: Regime; label: string }[] = [
  { id: 'MEI', label: 'MEI (Microempreendedor Individual)' },
  { id: 'SIMPLES', label: 'Simples Nacional' },
  { id: 'PF', label: 'Pessoa Fisica' },
]

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

export default function Perfil({ sessao, onVoltar, onAtualizarUsuario }: Props) {
  const [perfil, setPerfil] = useState<DadosPerfil | null>(null)
  const [nome, setNome] = useState('')
  const [regime, setRegime] = useState<Regime>(sessao.user.regime)
  const [erroCarregar, setErroCarregar] = useState<string | null>(null)
  const [erroSalvar, setErroSalvar] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [ok, setOk] = useState(false)

  useEffect(() => {
    let ativo = true
    async function carregar() {
      try {
        const p = await getPerfil(sessao.token)
        if (!ativo) return
        setPerfil(p)
        setNome(p.nome ?? '')
        setRegime(p.regime)
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
    if (!ok) return
    const id = setTimeout(() => setOk(false), 2500)
    return () => clearTimeout(id)
  }, [ok])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErroSalvar(null)
    setOk(false)
    setSalvando(true)
    try {
      const nomeFinal = nome.trim() === '' ? null : nome.trim()
      await atualizarPerfil(sessao.token, { nome: nomeFinal, regime })
      const atualizado = await getPerfil(sessao.token)
      setPerfil(atualizado)
      setNome(atualizado.nome ?? '')
      setRegime(atualizado.regime)
      onAtualizarUsuario(atualizado.nome, atualizado.regime)
      setOk(true)
    } catch (e) {
      setErroSalvar(msgErro(e))
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

  if (!perfil) {
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
        <h2>Perfil</h2>

        <form onSubmit={handleSubmit} className="perfil-form">
          <label>
            E-mail
            <input type="text" value={perfil.email} readOnly disabled />
          </label>

          <label>
            Nome
            <input
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={100}
              disabled={salvando}
              placeholder="Como quer ser chamado"
            />
          </label>

          <label>
            Regime
            <select
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime)}
              disabled={salvando}
            >
              {REGIMES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Criado em
            <input type="text" value={formatData(perfil.criado_em)} readOnly disabled />
          </label>

          {erroSalvar && <p role="alert">{erroSalvar}</p>}
          {ok && (
            <p role="status" className="perfil-ok">
              Perfil atualizado.
            </p>
          )}

          <button type="submit" disabled={salvando}>
            {salvando ? 'Salvando...' : 'Salvar alteracoes'}
          </button>
        </form>
      </section>
    </main>
  )
}