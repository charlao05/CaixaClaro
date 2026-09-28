import './App.css'
import { useState } from 'react'
import { carregarSessao, limparSessao, type Sessao } from './services/session'
import { logout as apiLogout } from './services/auth'
import Login from './screens/Login'
import Register from './screens/Register'
import Dashboard from './screens/Dashboard'

type ViewNaoAutenticado = 'login' | 'register'

export default function App() {
  const [sessao, setSessao] = useState<Sessao | null>(() => carregarSessao())
  const [view, setView] = useState<ViewNaoAutenticado>('login')

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

  return <Dashboard sessao={sessao} onLogout={handleLogout} />
}