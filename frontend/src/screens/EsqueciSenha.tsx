import { useState, type FormEvent } from 'react'
import { esqueciSenha } from '../services/auth'
import { ApiError } from '../services/api'

type Props = {
  onVoltar: () => void
  onCodigoEnviado: (email: string) => void
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

export default function EsqueciSenha({ onVoltar, onCodigoEnviado }: Props) {
  const [email, setEmail] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setCarregando(true)
    try {
      await esqueciSenha(email)
      onCodigoEnviado(email)
    } catch (err) {
      setErro(msgErro(err))
    } finally {
      setCarregando(false)
    }
  }

  return (
    <main>
      <h1>CaixaClaro</h1>
      <h2>Recuperar senha</h2>
      <p>
        Informe seu e-mail. Se sua conta tiver Telegram vinculado, enviaremos
        um código de 6 dígitos para você redefinir a senha.
      </p>
      <p className="assinatura-nota">
        Este recurso usa o Telegram. Se você ainda não vinculou, acesse Perfil → Telegram antes de continuar.
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
            autoFocus
          />
        </label>
        {erro && <p role="alert">{erro}</p>}
        <button type="submit" disabled={carregando}>
          {carregando ? 'Enviando...' : 'Enviar código'}
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