import { useState, type FormEvent } from 'react'
import { redefinirSenha } from '../services/auth'
import { ApiError } from '../services/api'

type Props = {
  emailInicial: string
  onVoltar: () => void
  onSucesso: () => void
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

function msgErro(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter
      ? `${e.message} Tente novamente em ${e.retryAfter}s.`
      : e.message
  }
  if (e instanceof Error) return e.message
  return 'Erro inesperado.'
}

export default function RedefinirSenha({ emailInicial, onVoltar, onSucesso }: Props) {
  const [email, setEmail] = useState(emailInicial)
  const [codigo, setCodigo] = useState('')
  const [senha, setSenha] = useState('')
  const [senha2, setSenha2] = useState('')
  const [mostrarSenha, setMostrarSenha] = useState(false)
  const [mostrarSenha2, setMostrarSenha2] = useState(false)
  const [senha2Erro, setSenha2Erro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)

    if (senha !== senha2) {
      setSenha2Erro('As senhas não conferem.')
      return
    }

    setCarregando(true)
    try {
      await redefinirSenha(email, codigo, senha)
      onSucesso()
    } catch (err) {
      setErro(msgErro(err))
    } finally {
      setCarregando(false)
    }
  }

  return (
    <main>
      <h1>CaixaClaro</h1>
      <h2>Redefinir senha</h2>
      <p>
        Digite o código que enviamos no Telegram e escolha uma nova senha.
        O código vale por 15 minutos.
      </p>
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
          Código
          <input
            type="text"
            value={codigo}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 6)
              setCodigo(v)
            }}
            required
            disabled={carregando}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            autoFocus
          />
        </label>
        <label>
          Nova senha
          <div className="campo-senha">
            <input
              type={mostrarSenha ? 'text' : 'password'}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              minLength={8}
              maxLength={72}
              disabled={carregando}
              autoComplete="new-password"
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
        <label>
          Confirmar nova senha
          <div className="campo-senha">
            <input
              type={mostrarSenha2 ? 'text' : 'password'}
              value={senha2}
              onChange={(e) => {
                setSenha2(e.target.value)
                if (senha2Erro) setSenha2Erro(null)
              }}
              required
              minLength={8}
              maxLength={72}
              disabled={carregando}
              autoComplete="new-password"
              aria-invalid={senha2Erro !== null}
            />
            <button
              type="button"
              className="campo-senha-toggle"
              onClick={() => setMostrarSenha2((v) => !v)}
              disabled={carregando}
              aria-label={mostrarSenha2 ? 'Ocultar senha' : 'Mostrar senha'}
              tabIndex={-1}
            >
              <IconeOlho aberto={mostrarSenha2} />
            </button>
          </div>
        </label>
        {senha2Erro && <p role="alert">{senha2Erro}</p>}
        {erro && <p role="alert">{erro}</p>}
        <button type="submit" disabled={carregando}>
          {carregando ? 'Redefinindo...' : 'Redefinir senha'}
        </button>
      </form>
      <p>
        <button type="button" onClick={onVoltar} disabled={carregando}>
          Voltar ao login
        </button>
      </p>
    </main>
  )
}