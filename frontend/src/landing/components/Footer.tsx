import Logo from './Logo'
import { NAV_LINKS } from './Header'

type Props = {
  onEntrar: () => void
  onComecar: () => void
}

/* PLACEHOLDER: páginas ainda sem destino confirmado. Substituir por links reais quando existirem. */
const LEGAL_PENDENTES = ['Privacidade', 'Termos de uso', 'Contato']

export default function Footer({ onEntrar, onComecar }: Props) {
  return (
    <footer className="lp-footer">
      <div className="lp-container">
        <div className="lp-footer-grid">
          <div className="lp-footer-brand">
            <Logo />
            <p>
              Organização e interpretação de informações financeiras e fiscais em linguagem simples.
            </p>
          </div>

          <div className="lp-footer-cols">
            <nav className="lp-footer-col" aria-label="Navegação do rodapé">
              <h3>Navegação</h3>
              <ul>
                {NAV_LINKS.map((link) => (
                  <li key={link.href}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </nav>

            <div className="lp-footer-col">
              <h3>Acesso</h3>
              <ul>
                <li>
                  <button type="button" className="lp-btn-link" onClick={onEntrar}>
                    Entrar
                  </button>
                </li>
                <li>
                  <button type="button" className="lp-btn-link" onClick={onComecar}>
                    Criar conta
                  </button>
                </li>
              </ul>
            </div>

            <div className="lp-footer-col">
              <h3>Institucional</h3>
              <ul>
                {LEGAL_PENDENTES.map((item) => (
                  <li key={item}>
                    <span className="lp-soon">
                      {item}
                      <small>em breve</small>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="lp-footer-bottom">
          <span>© {new Date().getFullYear()} CaixaClaro</span>
          <span>
            O CaixaClaro não é banco, não movimenta dinheiro e não substitui um contador.
          </span>
        </div>
      </div>
    </footer>
  )
}
