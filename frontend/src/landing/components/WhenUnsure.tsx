import { Check, MessageCircleQuestion, ScanSearch } from 'lucide-react'

export default function WhenUnsure() {
  return (
    <section className="lp-section" aria-labelledby="falta-info-titulo">
      <div className="lp-container">
        <div className="lp-unsure lp-reveal">
          <div className="lp-unsure-copy">
            <span className="lp-eyebrow">O jeito CaixaClaro</span>
            <h2 id="falta-info-titulo" className="lp-h2">
              Clareza também é saber quando falta informação.
            </h2>
            <p className="lp-lead">
              Nem toda movimentação pode ser entendida apenas olhando para o extrato. Quando faltar
              contexto, o CaixaClaro pergunta. Você confirma. E a interpretação fica mais clara.
            </p>
            <blockquote>Quando não dá para saber, o CaixaClaro pergunta.</blockquote>
          </div>

          <ol className="lp-unsure-flow" aria-label="O que acontece quando falta contexto">
            <li className="lp-flow-step">
              <span className="lp-flow-dot" aria-hidden="true">
                <ScanSearch size={20} />
              </span>
              <div>
                <h3>O CaixaClaro olha a movimentação</h3>
                <p>Valor, data, descrição e o que mais estiver disponível.</p>
              </div>
            </li>
            <li className="lp-flow-step is-ask">
              <span className="lp-flow-dot" aria-hidden="true">
                <MessageCircleQuestion size={20} />
              </span>
              <div>
                <h3>Se não dá para ter certeza, ele pergunta</h3>
                <p>Em vez de adivinhar, a movimentação vai para revisão.</p>
              </div>
            </li>
            <li className="lp-flow-step is-done">
              <span className="lp-flow-dot" aria-hidden="true">
                <Check size={20} />
              </span>
              <div>
                <h3>Você confirma o contexto</h3>
                <p>Com a sua resposta, a interpretação fica mais clara.</p>
              </div>
            </li>
          </ol>
        </div>
      </div>
    </section>
  )
}
