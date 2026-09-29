import { ArrowRight } from 'lucide-react'

type Props = {
  onComecar: () => void
  onEntrar: () => void
}

export default function FinalCta({ onComecar, onEntrar }: Props) {
  return (
    <section className="lp-section" aria-labelledby="cta-final-titulo" style={{ paddingBottom: 0 }}>
      <div className="lp-container">
        <div className="lp-final lp-reveal">
          <h2 id="cta-final-titulo">Seu dinheiro não precisa parecer complicado.</h2>
          <p>Comece entendendo o que já aconteceu.</p>
          <div className="lp-hero-ctas">
            <button type="button" className="lp-btn lp-btn-primary" onClick={onComecar}>
              Começar agora
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <button type="button" className="lp-btn lp-btn-ghost" onClick={onEntrar}>
              Já tenho conta
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
