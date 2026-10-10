import { useState, type FormEvent } from 'react'
import { register, type Regime } from '../services/auth'
import { salvarSessao, type Sessao } from '../services/session'
import { ApiError } from '../services/api'
import { apenasDigitos, formatarCPF, validarCPF } from '../utils/cpf'

type Props = {
  onRegistrar: (s: Sessao) => void
  onIrParaLogin: () => void
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

// O CaixaClaro serve quem é MEI, quem trabalha no CPF, quem tem empresa
// pequena e quem ainda está começando. Ninguém é tratado como MEI por omissão.
const PERFIS: { id: string; regime: Regime; label: string; ajuda: string }[] = [
  {
    id: 'mei',
    regime: 'MEI',
    label: 'Sou MEI',
    ajuda: 'Tenho CNPJ de microempreendedor individual.',
  },
  {
    id: 'autonomo',
    regime: 'PF',
    label: 'Trabalho por conta própria, sem CNPJ',
    ajuda: 'Faço serviços, bicos ou vendas no meu CPF.',
  },
  {
    id: 'simples',
    regime: 'SIMPLES',
    label: 'Tenho empresa no Simples Nacional',
    ajuda: 'Microempresa ou empresa de pequeno porte.',
  },
  {
    id: 'assalariado',
    regime: 'PF',
    label: 'Tenho emprego ou aposentadoria',
    ajuda: 'Quero entender meu dinheiro, com ou sem renda extra.',
  },
  {
    id: 'comecando',
    regime: 'PF',
    label: 'Estou começando e ainda não sei',
    ajuda: 'Tudo bem. Você começa como pessoa física e muda depois, no Perfil.',
  },
]

export default function Register({ onRegistrar, onIrParaLogin }: Props) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [senha2, setSenha2] = useState('')
  const [mostrarSenha, setMostrarSenha] = useState(false)
  const [mostrarSenha2, setMostrarSenha2] = useState(false)
  const [cpf, setCpf] = useState('')
  const [perfil, setPerfil] = useState('')
  const [cpfErro, setCpfErro] = useState<string | null>(null)
  const [senha2Erro, setSenha2Erro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  function handleCpfChange(raw: string) {
    setCpf(formatarCPF(raw))
    if (cpfErro) setCpfErro(null)
  }

  function handleCpfBlur() {
    if (apenasDigitos(cpf).length === 0) return
    if (!validarCPF(cpf)) {
      setCpfErro('CPF inválido — verifique os dígitos.')
    } else {
      setCpfErro(null)
    }
  }

  function handleSenha2Change(v: string) {
    setSenha2(v)
    if (senha2Erro) setSenha2Erro(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)

    const escolhido = PERFIS.find((p) => p.id === perfil)
    if (!escolhido) {
      setErro('Escolha a opção que mais parece com você.')
      return
    }

    if (!validarCPF(cpf)) {
      setCpfErro('CPF inválido — verifique os dígitos.')
      return
    }

    if (senha !== senha2) {
      setSenha2Erro('As senhas não conferem.')
      return
    }

    setCarregando(true)
    try {
      const r = await register(email, senha, cpf, escolhido.regime)
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
      <p className="assinatura-nota">
        Você tem 7 dias para experimentar, sem informar cartão.
      </p>
      <form onSubmit={handleSubmit}>
        <fieldset className="cadastro-perfis">
          <legend>Como você trabalha hoje?</legend>
          {PERFIS.map((p) => (
            <label key={p.id} className="cadastro-perfil">
              <input
                type="radio"
                name="perfil"
                value={p.id}
                checked={perfil === p.id}
                onChange={() => setPerfil(p.id)}
                disabled={carregando}
              />
              <span>
                <strong>{p.label}</strong>
                <small>{p.ajuda}</small>
              </span>
            </label>
          ))}
        </fieldset>
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
          Confirmar senha
          <div className="campo-senha">
            <input
              type={mostrarSenha2 ? 'text' : 'password'}
              value={senha2}
              onChange={(e) => handleSenha2Change(e.target.value)}
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
        <label>
          CPF
          <input
            type="text"
            value={cpf}
            onChange={(e) => handleCpfChange(e.target.value)}
            onBlur={handleCpfBlur}
            required
            disabled={carregando}
            autoComplete="off"
            inputMode="numeric"
            maxLength={14}
            aria-invalid={cpfErro !== null}
          />
        </label>
        <p className="assinatura-nota">
          O CPF identifica a sua conta e é usado para gerar a cobrança da
          assinatura. Ele fica guardado cifrado.
        </p>
        {senha2Erro && <p role="alert">{senha2Erro}</p>}
        {cpfErro && <p role="alert">{cpfErro}</p>}
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