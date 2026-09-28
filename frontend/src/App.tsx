import { useState } from 'react'
import { carregarSessao, limparSessao, type Sessao } from './services/session'
import { logout as apiLogout } from './services/auth'
import Login from './screens/Login'
import Home from './screens/Home'

export default function App() {
  const [sessao, setSessao] = useState<Sessao | null>(() => carregarSessao())

  async function handleLogout() {
    if (!sessao) return
    try {
      await apiLogout(sessao.token)
    } catch {
      // falha no backend nao impede logout local
    }
    limparSessao()
    setSessao(null)
  }

  if (!sessao) {
    return <Login onLogin={setSessao} />
  }

  return <Home usuario={sessao.user} onLogout={handleLogout} />
}