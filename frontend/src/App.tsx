import './App.css'
import { useEffect, useState } from 'react'
import {
  carregarSessao,
  limparSessao,
  salvarSessao,
  type Sessao,
} from './services/session'
import { logout as apiLogout, type Regime } from './services/auth'
import Login from './screens/Login'
import Register from './screens/Register'
import Dashboard from './screens/Dashboard'
import Ingestao from './screens/Ingestao'
import Revisao from './screens/Revisao'
import Alertas from './screens/Alertas'
import Perfil from './screens/Perfil'
import ListaTransacoes from './screens/ListaTransacoes'
import Opiniao from './screens/Opiniao'
import Contas from './screens/Contas'
import Assinatura from './screens/Assinatura'
import Negocio from './screens/Negocio'
import LandingPage from './landing/LandingPage'

type ViewNaoAutenticado = 'landing' | 'login' | 'register'

const VIEW_KEY = 'caixaclaro:view'

function isViewNaoAutenticado(value: string | null): value is ViewNaoAutenticado {
  return value === 'landing' || value === 'login' || value === 'register'
}
type ViewAutenticado =
  | 'dashboard'
  | 'ingestao'
  | 'revisao'
  | 'alertas'
  | 'perfil'
  | 'transacoes'
  | 'opiniao'
  | 'contas'
  | 'assinatura'
  | 'negocio'

const VIEW_AUTH_KEY = 'caixaclaro:viewAuth'
const SELECTED_TX_KEY = 'caixaclaro:selectedTxId'

function isViewAutenticado(value: string | null): value is ViewAutenticado {
  return (
    value === 'dashboard' ||
    value === 'ingestao' ||
    value === 'revisao' ||
    value === 'alertas' ||
    value === 'perfil' ||
    value === 'transacoes' ||
    value === 'opiniao' ||
    value === 'contas' ||
    value === 'assinatura' ||
    value === 'negocio'
  )
}

function carregarViewAuth(): ViewAutenticado {
  const raw = sessionStorage.getItem(VIEW_AUTH_KEY)
  return isViewAutenticado(raw) ? raw : 'dashboard'
}

function carregarSelectedTxId(): string | null {
  return sessionStorage.getItem(SELECTED_TX_KEY)
}

export default function App() {
  const [sessao, setSessao] = useState<Sessao | null>(() => carregarSessao())
  const [view, setView] = useState<ViewNaoAutenticado>(() => {
    const salvo = sessionStorage.getItem(VIEW_KEY)
    return isViewNaoAutenticado(salvo) ? salvo : 'landing'
  })

  useEffect(() => {
    sessionStorage.setItem(VIEW_KEY, view)
  }, [view])
  const [viewAuth, setViewAuth] = useState<ViewAutenticado>(() => carregarViewAuth())
  const [selectedTxId, setSelectedTxId] = useState<string | null>(() => carregarSelectedTxId())

  useEffect(() => {
    sessionStorage.setItem(VIEW_AUTH_KEY, viewAuth)
  }, [viewAuth])

  useEffect(() => {
    if (selectedTxId === null) {
      sessionStorage.removeItem(SELECTED_TX_KEY)
    } else {
      sessionStorage.setItem(SELECTED_TX_KEY, selectedTxId)
    }
  }, [selectedTxId])

  async function handleLogout() {
    if (!sessao) return
    try {
      await apiLogout(sessao.token)
    } catch {
      // falha no backend nao impede logout local
    }
    limparSessao()
    setSessao(null)
    setView('login')
    setViewAuth('dashboard')
    setSelectedTxId(null)
    sessionStorage.removeItem(VIEW_AUTH_KEY)
    sessionStorage.removeItem(SELECTED_TX_KEY)
  }

  function handleAtualizarUsuario(nome: string | null, regime: Regime) {
    if (!sessao) return
    const nova: Sessao = {
      ...sessao,
      user: { ...sessao.user, nome, regime },
    }
    salvarSessao(nova)
    setSessao(nova)
  }

  if (!sessao) {
    if (view === 'landing') {
      return (
        <LandingPage
          onComecar={() => setView('register')}
          onEntrar={() => setView('login')}
        />
      )
    }
    if (view === 'register') {
      return (
        <Register
          onRegistrar={setSessao}
          onIrParaLogin={() => setView('login')}
        />
      )
    }
    return (
      <Login
        onLogin={setSessao}
        onIrParaRegister={() => setView('register')}
      />
    )
  }

  if (viewAuth === 'ingestao') {
    return (
      <Ingestao sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  if (viewAuth === 'revisao') {
    return (
      <Revisao sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  if (viewAuth === 'alertas') {
    return (
      <Alertas sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  if (viewAuth === 'negocio') {
    return (
      <Negocio sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  if (viewAuth === 'perfil') {
    return (
      <Perfil
        sessao={sessao}
        onVoltar={() => setViewAuth('dashboard')}
        onAtualizarUsuario={handleAtualizarUsuario}
      />
    )
  }

  if (viewAuth === 'transacoes') {
    return (
      <ListaTransacoes
        sessao={sessao}
        onVoltar={() => setViewAuth('dashboard')}
        onSelecionar={(id) => {
          setSelectedTxId(id)
          setViewAuth('opiniao')
        }}
      />
    )
  }

  if (viewAuth === 'opiniao' && selectedTxId) {
    return (
      <Opiniao
        sessao={sessao}
        txId={selectedTxId}
        onVoltar={() => {
          setSelectedTxId(null)
          setViewAuth('transacoes')
        }}
      />
    )
  }

  if (viewAuth === 'contas') {
    return (
      <Contas sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  if (viewAuth === 'assinatura') {
    return (
      <Assinatura sessao={sessao} onVoltar={() => setViewAuth('dashboard')} />
    )
  }

  return (
    <Dashboard
      sessao={sessao}
      onLogout={handleLogout}
      onNovaIngestao={() => setViewAuth('ingestao')}
      onRevisar={() => setViewAuth('revisao')}
      onAlertas={() => setViewAuth('alertas')}
      onPerfil={() => setViewAuth('perfil')}
      onTransacoes={() => setViewAuth('transacoes')}
      onContas={() => setViewAuth('contas')}
      onAssinatura={() => setViewAuth('assinatura')}
      onNegocio={() => setViewAuth('negocio')}
    />
  )
}
