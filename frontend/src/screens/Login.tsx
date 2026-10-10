import { useState, type FormEvent } from 'react'
import { login } from '../services/auth'
import { salvarSessao, type Sessao } from '../services/session'
import { ApiError } from '../services/api'

type Props = {
  aviso?: string | null
  onLogin: (s: Sessao) => void
  onIrParaRegister: () => void
  onIrParaEsqueciSenha: () => void
}

function IconeOlho({ aberto }: { aberto: boolean }) {
  if (aberto) {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    )
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

export default function Login({ aviso = null, onLogin, onIrParaRegister, onIrParaEsqueciSenha }: Props) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [mostrarSenha, setMostrarSenha] = useState(false)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setCarregando(true)
    try {
      const r = await login(email, senha)
      const sessao: Sessao = {
        token: r.token,
        expiresAt: r.expires_at,
        user: r.user,
      }
      salvarSessao(sessao)
      onLogin(sessao)
    } catch (e) {
      if (e instanceof ApiError) {
        setErro(
          e.retryAfter
            ? `${e.message} Tente novamente em ${e.retryAfter}s.`
            : e.message,
        )
      } else {
        setErro('Erro inesperado.')
      }
    } finally {
      setCarregando(false)
    }
  }

  return (
    <main>
      <h1>CaixaClaro</h1>
      <form onSubmit={handleSubmit}>
        {aviso && !erro && (
          <p role="status" className="revisao-feedback">
            {aviso}
          </p>
        )}
        <label>
          E-mail
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={carregando}
            autoComplete="username"
          />
        </label>
        <label>
          Senha
          <div className="campo-senha">
            <input
              type={mostrarSenha ? 'text' : 'password'}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              disabled={carregando}
              autoComplete="current-password"
            />
            <button
              type="button"
              className="campo-senha-toggle"
              onClick={() => setMostrarSenha((v) => !v)}
              disabled={carregando}
              aria-label={mostrarSenha ? 'Ocultar senha' : 'Mostrar senha'}
              tabIndex={-1}
            >
              <IconeOlho aberto={mostrarSenha} />
            </button>
          </div>
        </label>
        <div className="conta-acoes">
          <button
            type="button"
            onClick={onIrParaEsqueciSenha}
            disabled={carregando}
          >
            Esqueci minha senha
          </button>
        </div>
        {erro && <p role="alert">{erro}</p>}
        <button type="submit" disabled={carregando}>
          {carregando ? 'Entrando...' : 'Entrar'}
        </button>
      </form>
      <p>
        Não tem conta?{' '}
        <button type="button" onClick={onIrParaRegister} disabled={carregando}>
          Criar conta
        </button>
      </p>
    </main>
  )
}