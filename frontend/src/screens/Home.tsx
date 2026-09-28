import type { Usuario } from '../services/auth'

type Props = {
  usuario: Usuario
  onLogout: () => void
}

export default function Home({ usuario, onLogout }: Props) {
  return (
    <main>
      <h1>CaixaClaro</h1>
      <p>Logado como {usuario.email}</p>
      <p>Regime: {usuario.regime}</p>
      <button type="button" onClick={onLogout}>
        Sair
      </button>
    </main>
  )
}