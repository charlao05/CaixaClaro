import './App.css'
import { useState } from 'react'
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

type ViewNaoAutenticado = 'login' | 'register'
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

export default function App() {
  const [sessao, setSessao] = useState<Sessao | null>(() => carregarSessao())
  const [view, setView] = useState<ViewNaoAutenticado>('login')
  const [viewAuth, setViewAuth] = useState<ViewAutenticado>('dashboard')
  const [selectedTxId, setSelectedTxId] = useState<string | null>(null)

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
    />
  )
}