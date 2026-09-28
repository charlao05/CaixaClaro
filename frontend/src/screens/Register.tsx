import { useState, type FormEvent } from 'react'
import { register } from '../services/auth'
import { salvarSessao, type Sessao } from '../services/session'
import { ApiError } from '../services/api'

type Props = {
  onRegistrar: (s: Sessao) => void
  onIrParaLogin: () => void
}

export default function Register({ onRegistrar, onIrParaLogin }: Props) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [cpf, setCpf] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setCarregando(true)
    try {
      const r = await register(email, senha, cpf)
      const sessao: Sessao = {
        token: r.token,
        expiresAt: r.expires_at,
        user: r.user,
      }
      salvarSessao(sessao)
      onRegistrar(sessao)
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
      <h2>Criar conta</h2>
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
            minLength={8}
            maxLength={72}
            disabled={carregando}
            autoComplete="new-password"
          />
        </label>
        <label>
          CPF
          <input
            type="text"
            value={cpf}
            onChange={(e) => setCpf(e.target.value)}
            required
            disabled={carregando}
            autoComplete="off"
          />
        </label>
        {erro && <p role="alert">{erro}</p>}
        <button type="submit" disabled={carregando}>
          {carregando ? 'Criando conta...' : 'Criar conta'}
        </button>
      </form>
      <p>
        Já tem conta?{' '}
        <button type="button" onClick={onIrParaLogin} disabled={carregando}>
          Entrar
        </button>
      </p>
    </main>
  )
}