import './App.css'
import { useState } from 'react'
import { carregarSessao, limparSessao, type Sessao } from './services/session'
import { logout as apiLogout } from './services/auth'
import Login from './screens/Login'
import Register from './screens/Register'
import Dashboard from './screens/Dashboard'
import Ingestao from './screens/Ingestao'
import Revisao from './screens/Revisao'
import Alertas from './screens/Alertas'

type ViewNaoAutenticado = 'login' | 'register'
type ViewAutenticado = 'dashboard' | 'ingestao' | 'revisao' | 'alertas'

export default function App() {
  const [sessao, setSessao] = useState<Sessao | null>(() => carregarSessao())
  const [view, setView] = useState<ViewNaoAutenticado>('login')
  const [viewAuth, setViewAuth] = useState<ViewAutenticado>('dashboard')

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
      <Ingestao
        sessao={sessao}
        onVoltar={() => setViewAuth('dashboard')}
      />
    )
  }

  if (viewAuth === 'revisao') {
    return (
      <Revisao
        sessao={sessao}
        onVoltar={() => setViewAuth('dashboard')}
      />
    )
  }

  if (viewAuth === 'alertas') {
    return (
      <Alertas
        sessao={sessao}
        onVoltar={() => setViewAuth('dashboard')}
      />
    )
  }

  return (
    <Dashboard
      sessao={sessao}
      onLogout={handleLogout}
      onNovaIngestao={() => setViewAuth('ingestao')}
      onRevisar={() => setViewAuth('revisao')}
      onAlertas={() => setViewAuth('alertas')}
    />
  )
}