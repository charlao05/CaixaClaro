import { Eye, Layers, MessageCircleQuestion, Upload, type LucideIcon } from 'lucide-react'

type Step = {
  num: string
  title: string
  text: string
  visual: string
  icon: LucideIcon
  highlight?: boolean
}

const STEPS: Step[] = [
  {
    num: '01',
    title: 'Traga suas movimentações',
    text: 'Envie suas informações financeiras pelo próprio CaixaClaro ou, se quiser, conecte suas contas via Open Finance.',
    visual: 'Envio manual ou Open Finance',
    icon: Upload,
  },
  {
    num: '02',
    title: 'O CaixaClaro organiza e interpreta',
    text: 'Ele ajuda a distinguir cada tipo de movimentação e explica o que ela pode representar, sem termos difíceis.',
    visual: 'Explicação em linguagem simples',
    icon: Layers,
  },
  {
    num: '03',
    title: 'Quando faltar contexto, ele pergunta',
    text: 'Se só o extrato não basta para entender uma movimentação, o CaixaClaro pede que você confirme. Sem chutar.',
    visual: '"De onde veio este Pix?"',
    icon: MessageCircleQuestion,
    highlight: true,
  },
  {
    num: '04',
    title: 'Você acompanha',
    text: 'Painel, lista de transações, alertas e o parecer fiscal ficam reunidos para você consultar quando precisar.',
    visual: 'Painel, transações e alertas',
    icon: Eye,
  },
]

export default function HowItWorks() {
  return (
    <section id="como-funciona" className="lp-section" aria-labelledby="como-funciona-titulo">
      <div className="lp-container">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">Como funciona</span>
          <h2 id="como-funciona-titulo" className="lp-h2">
            Quatro passos, nenhum termo contábil.
          </h2>
          <p className="lp-lead">
            Você não precisa entender de contabilidade para começar. Precisa só querer entender o
            próprio dinheiro.
          </p>
        </div>

        <ol className="lp-steps" aria-label="Etapas">
          {STEPS.map((step, index) => {
            const Icon = step.icon
            return (
              <li
                key={step.num}
                className={`lp-step lp-reveal${step.highlight ? ' is-ask' : ''}`}
                style={{ transitionDelay: `${index * 80}ms` }}
              >
                <div className="lp-step-bars" aria-hidden="true">
                  {STEPS.map((s, i) => (
                    <span key={s.num} className={i <= index ? 'is-on' : undefined} />
                  ))}
                </div>
                <span className="lp-step-num">ETAPA {step.num}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
                <div className="lp-step-visual">
                  <Icon size={18} aria-hidden="true" />
                  {step.visual}
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
