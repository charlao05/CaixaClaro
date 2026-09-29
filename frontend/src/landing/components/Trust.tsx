import { Ban, Info, KeyRound, Landmark, Lock, ShieldCheck, type LucideIcon } from 'lucide-react'

type TrustItem = {
  title: string
  text: string
  icon: LucideIcon
}

const TRUST: TrustItem[] = [
  {
    title: 'Não movimenta seu dinheiro',
    text: 'O CaixaClaro lê informações para organizar e explicar. Ele não faz Pix, transferências, saques ou investimentos.',
    icon: Ban,
  },
  {
    title: 'Open Finance, se você quiser',
    text: 'Conectar suas contas é opcional. Você decide se e quando fazer isso.',
    icon: Landmark,
  },
  {
    title: 'Acesso com sua conta',
    text: 'Para ver seus dados é preciso entrar com e-mail e senha cadastrados.',
    icon: KeyRound,
  },
  {
    title: 'Seus dados, só seus',
    text: 'Cada pessoa acessa apenas as próprias informações dentro da aplicação.',
    icon: Lock,
  },
]

const LIMITES = [
  'Não substitui um contador em apurações formais',
  'Não recomenda compra, venda ou troca de investimentos',
  'Não promete redução de impostos ou economia',
  'Não toma decisões financeiras por você',
]

export default function Trust() {
  return (
    <section id="seguranca" className="lp-section" aria-labelledby="seguranca-titulo">
      <div className="lp-container">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">
            <ShieldCheck size={15} aria-hidden="true" />
            Segurança e transparência
          </span>
          <h2 id="seguranca-titulo" className="lp-h2">
            Confiança começa dizendo o que a gente faz e o que não faz.
          </h2>
        </div>

        <ul className="lp-trust-grid">
          {TRUST.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.title} className="lp-trust-card lp-reveal">
                <Icon size={24} aria-hidden="true" />
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </li>
            )
          })}
        </ul>

        <div className="lp-limits lp-reveal">
          <div className="lp-limits-copy">
            <span className="lp-eyebrow" style={{ color: 'var(--lp-blue)' }}>
              Limites do CaixaClaro
            </span>
            <h3>
              O CaixaClaro organiza e explica informações financeiras e fiscais. Ele não é um
              escritório de contabilidade e não substitui um profissional em apurações formais.
            </h3>
            <p>
              Quando uma informação não for suficiente para uma interpretação segura, o sistema pode
              pedir que você confirme o contexto.
            </p>
          </div>
          <ul className="lp-limits-list">
            {LIMITES.map((limite) => (
              <li key={limite}>
                <Info size={18} aria-hidden="true" />
                {limite}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
