import {
  Bell,
  CreditCard,
  FileText,
  Landmark,
  LayoutDashboard,
  ListChecks,
  MessageCircleQuestion,
  Send,
  type LucideIcon,
} from 'lucide-react'

type Feature = {
  name: string
  title: string
  text: string
  icon: LucideIcon
  wide?: boolean
  blue?: boolean
  tag?: string
}

/* Somente recursos existentes na aplicação atual (ver frontend/src/screens). */
const FEATURES: Feature[] = [
  {
    name: 'Revisão',
    title: 'Quando uma movimentação precisa de contexto, você participa da resposta.',
    text: 'O CaixaClaro não precisa fingir certeza. Ele mostra o que ficou em aberto e você confirma o que aconteceu.',
    icon: MessageCircleQuestion,
    wide: true,
  },
  {
    name: 'Painel',
    title: 'Veja sua vida financeira de forma mais clara.',
    text: 'Uma visão resumida das informações que você já trouxe para o CaixaClaro.',
    icon: LayoutDashboard,
    blue: true,
  },
  {
    name: 'Transações',
    title: 'Entenda suas movimentações.',
    text: 'Entradas e saídas organizadas, cada uma com sua explicação.',
    icon: ListChecks,
  },
  {
    name: 'Parecer fiscal',
    title: 'Entenda melhor o possível impacto fiscal das movimentações.',
    text: 'Veja quais movimentações podem ter relevância fiscal, em linguagem simples. Não é uma apuração tributária definitiva.',
    icon: FileText,
    blue: true,
    wide: true,
  },
  {
    name: 'Alertas',
    title: 'Não dependa apenas da memória.',
    text: 'O CaixaClaro mostra o que precisa da sua resposta e, se você é MEI, avisa quando o faturamento do ano se aproxima do limite.',
    icon: Bell,
  },
  {
    name: 'Contas',
    title: 'Conecte suas contas quando quiser.',
    text: 'A conexão via Open Finance é opcional e serve para trazer suas movimentações. O CaixaClaro não movimenta dinheiro.',
    icon: Landmark,
    tag: 'Opcional',
  },
  {
    name: 'Telegram',
    title: 'Tenha um canal complementar de acompanhamento.',
    text: 'Vincule sua conta do CaixaClaro ao Telegram.',
    icon: Send,
    blue: true,
    tag: 'Complementar',
  },
  {
    name: 'Assinatura',
    title: 'Assine direto pela aplicação.',
    text: 'O fluxo de assinatura já está disponível dentro do CaixaClaro.',
    icon: CreditCard,
    tag: 'Planos em definição',
  },
]

export default function Features() {
  return (
    <section id="recursos" className="lp-section" aria-labelledby="recursos-titulo">
      <div className="lp-container">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">Recursos</span>
          <h2 id="recursos-titulo" className="lp-h2">
            O que o CaixaClaro faz hoje.
          </h2>
          <p className="lp-lead">
            Sem promessas para o futuro. Estes são os recursos que já existem na aplicação.
          </p>
        </div>

        <ul className="lp-features-grid">
          {FEATURES.map((feature) => {
            const Icon = feature.icon
            const classes = ['lp-feature', 'lp-reveal']
            if (feature.wide) classes.push('is-wide')
            if (feature.blue) classes.push('is-blue')
            return (
              <li key={feature.name} className={classes.join(' ')}>
                <span className="lp-feature-icon" aria-hidden="true">
                  <Icon size={22} />
                </span>
                <span className="lp-feature-name">{feature.name}</span>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
                {feature.tag && <span className="lp-feature-tag">{feature.tag}</span>}
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}
