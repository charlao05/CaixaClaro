import { Check, Minus, X } from 'lucide-react'

const ANTES = [
  'Extratos espalhados em vários lugares',
  'Planilhas e anotações soltas',
  'Termos difíceis de entender',
  'Movimentações sem contexto',
  'Medo de classificar algo errado',
]

const DEPOIS = [
  'Movimentações organizadas em um só lugar',
  'Explicações em linguagem simples',
  'Revisão quando algo precisa de contexto',
  'Alertas sobre o que merece atenção',
  'Conexão opcional via Open Finance',
  'Contexto antes de qualquer conclusão',
]

export default function BeforeAfter() {
  return (
    <section className="lp-section lp-ba" aria-labelledby="antes-depois-titulo">
      <div className="lp-container">
        <div className="lp-section-head is-center lp-reveal">
          <span className="lp-eyebrow">Antes e depois</span>
          <h2 id="antes-depois-titulo" className="lp-h2">
            Menos dúvida sobre o que já aconteceu.
          </h2>
        </div>

        <div className="lp-ba-grid">
          <div className="lp-ba-col is-before lp-reveal">
            <h3>
              <span className="lp-ba-badge" aria-hidden="true">
                <Minus size={18} />
              </span>
              Antes
            </h3>
            <ul className="lp-ba-list">
              {ANTES.map((item) => (
                <li key={item}>
                  <X size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="lp-ba-col is-after lp-reveal">
            <h3>
              <span className="lp-ba-badge" aria-hidden="true">
                <Check size={18} />
              </span>
              Com o CaixaClaro
            </h3>
            <ul className="lp-ba-list">
              {DEPOIS.map((item) => (
                <li key={item}>
                  <Check size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}
