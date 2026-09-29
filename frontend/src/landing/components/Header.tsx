import { useEffect, useState } from 'react'
import Logo from './Logo'

type Props = {
  onComecar: () => void
  onEntrar: () => void
}

export const NAV_LINKS = [
  { href: '#como-funciona', label: 'Como funciona' },
  { href: '#recursos', label: 'Recursos' },
  { href: '#seguranca', label: 'Segurança' },
  { href: '#duvidas', label: 'Dúvidas' },
]

export default function Header({ onComecar, onEntrar }: Props) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`lp-header${scrolled ? ' is-scrolled' : ''}`}>
      <div className="lp-container lp-header-inner">
        <Logo />
        <nav className="lp-nav" aria-label="Navegação principal">
          <ul>
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <a href={link.href}>{link.label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="lp-header-actions">
          <button type="button" className="lp-btn-link lp-header-login" onClick={onEntrar}>
            Entrar
          </button>
          <button type="button" className="lp-btn lp-btn-primary lp-btn-sm" onClick={onComecar}>
            Começar agora
          </button>
        </div>
      </div>
    </header>
  )
}
