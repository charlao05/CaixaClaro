import { Plus } from 'lucide-react'

const FAQ = [
  {
    q: 'O CaixaClaro é um banco?',
    a: 'Não. O CaixaClaro é uma aplicação para organizar e interpretar informações financeiras e fiscais. Ele não guarda nem movimenta o seu dinheiro.',
  },
  {
    q: 'Preciso conectar minha conta bancária?',
    a: 'Não necessariamente. A conexão via Open Finance é uma das formas de trazer suas movimentações. Você também pode enviar as informações diretamente pela aplicação.',
  },
  {
    q: 'O CaixaClaro movimenta meu dinheiro?',
    a: 'Não. Ele usa as informações das suas movimentações apenas para organizar e explicar. Não faz Pix, transferências, saques, pagamentos ou investimentos.',
  },
  {
    q: 'O CaixaClaro substitui um contador?',
    a: 'Não. Ele ajuda a organizar e entender suas informações, mas não substitui um profissional habilitado em apurações formais.',
  },
  {
    q: 'O CaixaClaro recomenda investimentos?',
    a: 'Não. Ele pode ajudar a diferenciar uma aplicação, um resgate, um rendimento ou uma transferência, mas não recomenda comprar, vender, manter ou trocar investimentos.',
  },
  {
    q: 'E se o CaixaClaro não conseguir entender uma movimentação?',
    a: 'Quando faltar contexto, ele pergunta. A movimentação vai para revisão e você confirma o que aconteceu.',
  },
  {
    q: 'Serve para empresas também?',
    a: 'O foco principal é quem trabalha por conta própria, como autônomos, profissionais liberais e MEIs. Pequenos negócios e empresas do Simples Nacional também podem usar.',
  },
  {
    q: 'Quanto custa?',
    a: 'Os planos ainda estão em definição. Assim que forem confirmados, as informações aparecerão aqui.',
  },
]

export default function Faq() {
  return (
    <section id="duvidas" className="lp-section" aria-labelledby="duvidas-titulo">
      <div className="lp-container lp-faq-layout">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">Dúvidas frequentes</span>
          <h2 id="duvidas-titulo" className="lp-h2">
            Perguntas diretas, respostas honestas.
          </h2>
        </div>

        <div className="lp-faq-list">
          {FAQ.map((item) => (
            <details key={item.q} className="lp-faq-item lp-reveal">
              <summary>
                {item.q}
                <span className="lp-faq-chevron" aria-hidden="true">
                  <Plus size={16} />
                </span>
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
