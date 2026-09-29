import { FileQuestion, HandCoins, ScrollText, Shuffle, TrendingUp } from 'lucide-react'

const PIX_OPCOES = ['Pagamento', 'Transferência', 'Empréstimo', 'Devolução']

export default function Problem() {
  return (
    <section className="lp-section" aria-labelledby="problema-titulo">
      <div className="lp-container">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">O problema</span>
          <h2 id="problema-titulo" className="lp-h2">
            O dinheiro entra e sai. Entender o que aconteceu é outra história.
          </h2>
        </div>

        <ul className="lp-problem-grid">
          <li className="lp-problem-card lp-reveal">
            <span className="lp-problem-icon" aria-hidden="true">
              <ScrollText size={22} />
            </span>
            <p>Você olha o extrato e não sabe o que realmente importa.</p>
          </li>

          <li className="lp-problem-card is-highlight lp-reveal">
            <span className="lp-problem-icon" aria-hidden="true">
              <Shuffle size={22} />
            </span>
            <p>Um Pix pode ser muita coisa.</p>
            <div className="lp-pix-chips" aria-label="Um Pix pode ser">
              {PIX_OPCOES.map((opcao) => (
                <span key={opcao}>{opcao}</span>
              ))}
            </div>
          </li>

          <li className="lp-problem-card lp-reveal">
            <span className="lp-problem-icon" aria-hidden="true">
              <HandCoins size={22} />
            </span>
            <p>Uma entrada de dinheiro nem sempre significa receita.</p>
          </li>

          <li className="lp-problem-card lp-reveal">
            <span className="lp-problem-icon" aria-hidden="true">
              <TrendingUp size={22} />
            </span>
            <p>Uma aplicação não é a mesma coisa que um rendimento.</p>
          </li>

          <li className="lp-problem-card lp-reveal">
            <span className="lp-problem-icon" aria-hidden="true">
              <FileQuestion size={22} />
            </span>
            <p>E quando chega a hora de organizar tudo, a dúvida aparece.</p>
          </li>
        </ul>
      </div>
    </section>
  )
}
