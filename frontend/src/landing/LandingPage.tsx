import { useRef } from 'react'
import './landing.css'
import { useReveal } from './useReveal'
import Header from './components/Header'
import Hero from './components/Hero'
import Problem from './components/Problem'
import BeforeAfter from './components/BeforeAfter'
import HowItWorks from './components/HowItWorks'
import Features from './components/Features'
import ProductShowcase from './components/ProductShowcase'
import WhenUnsure from './components/WhenUnsure'
import Trust from './components/Trust'
import Faq from './components/Faq'
import FinalCta from './components/FinalCta'
import Footer from './components/Footer'

type Props = {
  onComecar: () => void
  onEntrar: () => void
}

export default function LandingPage({ onComecar, onEntrar }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  useReveal(rootRef)

  return (
    <div className="lp" id="topo" ref={rootRef}>
      <a href="#conteudo" className="lp-skip">
        Pular para o conteúdo
      </a>
      <Header onComecar={onComecar} onEntrar={onEntrar} />
      <main id="conteudo" className="lp-main">
        <Hero onComecar={onComecar} />
        <Problem />
        <BeforeAfter />
        <HowItWorks />
        <Features />
        <ProductShowcase />
        <WhenUnsure />
        <Trust />
        <Faq />
        <FinalCta onComecar={onComecar} onEntrar={onEntrar} />
      </main>
      <Footer onComecar={onComecar} onEntrar={onEntrar} />
    </div>
  )
}
