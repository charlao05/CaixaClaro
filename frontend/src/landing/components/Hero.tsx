import { ArrowRight, Check, MessageCircleQuestion } from 'lucide-react'
import PhoneMockup from './PhoneMockup'

type Props = {
  onComecar: () => void
}

export default function Hero({ onComecar }: Props) {
  return (
    <section className="lp-hero" aria-labelledby="hero-titulo">
      <div className="lp-container lp-hero-grid">
        <div className="lp-hero-copy">
          <span className="lp-hero-pill">
            <span className="lp-hero-pill-dot" aria-hidden="true">
              <MessageCircleQuestion size={13} strokeWidth={2.5} />
            </span>
            Quando não dá para saber, ele pergunta
          </span>

          <h1 id="hero-titulo">
            Seu extrato fala. <em>O CaixaClaro explica.</em>
          </h1>

          <p className="lp-hero-sub">
            Organize suas entradas e saídas e entenda o que cada movimentação representa, em
            linguagem simples. Use as informações que você mesmo traz ou conecte suas contas via
            Open Finance, se preferir.
          </p>

          <div className="lp-hero-ctas">
            <button type="button" className="lp-btn lp-btn-primary" onClick={onComecar}>
              Começar agora
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <a href="#como-funciona" className="lp-btn lp-btn-ghost">
              Ver como funciona
            </a>
          </div>

          <ul className="lp-hero-notes" aria-label="Destaques">
            <li>
              <Check size={16} aria-hidden="true" />
              Feito para autônomos e MEIs
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              Open Finance opcional
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              Não movimenta seu dinheiro
            </li>
          </ul>
        </div>

        <div className="lp-hero-visual">
          <PhoneMockup />
        </div>
      </div>
    </section>
  )
}
