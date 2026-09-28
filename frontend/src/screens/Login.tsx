import { useState, type FormEvent } from 'react'
import { login } from '../services/auth'
import { salvarSessao, type Sessao } from '../services/session'
import { ApiError } from '../services/api'

type Props = {
  onLogin: (s: Sessao) => void
}

export default function Login({ onLogin }: Props) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
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
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            required
            disabled={carregando}
            autoComplete="current-password"
          />
        </label>
        {erro && <p role="alert">{erro}</p>}
        <button type="submit" disabled={carregando}>
          {carregando ? 'Entrando...' : 'Entrar'}
        </button>
      </form>
    </main>
  )
}