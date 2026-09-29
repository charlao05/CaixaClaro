import { Sparkle } from 'lucide-react'

export default function Logo() {
  return (
    <a href="#topo" className="lp-logo" aria-label="CaixaClaro, voltar ao topo">
      <span className="lp-logo-mark" aria-hidden="true">
        <Sparkle size={18} strokeWidth={2.4} />
      </span>
      <span className="lp-logo-text">
        Caixa<span>Claro</span>
      </span>
    </a>
  )
}
