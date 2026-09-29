import { Bell, Check, Info } from 'lucide-react'

const OPCOES = [
  'Pagamento de cliente',
  'Transferência entre minhas contas',
  'Devolução',
  'Empréstimo',
]

const ESCOLHIDA = 'Pagamento de cliente'

function IllustrativeTag() {
  return (
    <span className="lp-illustrative">
      <Info size={13} aria-hidden="true" />
      Dado ilustrativo
    </span>
  )
}

/* DADO ILUSTRATIVO: valores, contagens e mensagens abaixo são fictícios. */
export default function ProductShowcase() {
  return (
    <section className="lp-section lp-showcase" aria-labelledby="experiencia-titulo">
      <div className="lp-container">
        <div className="lp-section-head lp-reveal">
          <span className="lp-eyebrow">Por dentro do CaixaClaro</span>
          <h2 id="experiencia-titulo" className="lp-h2">
            Parece uma conversa, não uma planilha.
          </h2>
          <p className="lp-lead">
            Em vez de tabelas cheias de números, você vê cartões simples e responde o que for
            preciso.
          </p>
        </div>

        <div className="lp-show-grid">
          <div className="lp-show-panel lp-reveal">
            <div className="lp-show-panel-head">
              <h3>Revisão de movimentação</h3>
              <IllustrativeTag />
            </div>
            <div className="lp-chat">
              <p className="lp-bubble is-app">
                Recebi um <strong>Pix de R$ 650,00</strong> hoje às 10:12. Só pelo extrato não dá
                para saber o que ele representa. De onde veio esse dinheiro?
              </p>
              <div className="lp-options" role="list" aria-label="Opções de resposta ilustrativas">
                {OPCOES.map((opcao) => (
                  <span
                    key={opcao}
                    role="listitem"
                    className={opcao === ESCOLHIDA ? 'is-picked' : undefined}
                  >
                    {opcao === ESCOLHIDA && <Check size={14} aria-hidden="true" />}
                    {opcao}
                    {opcao === ESCOLHIDA && <span className="sr-only"> (selecionada)</span>}
                  </span>
                ))}
              </div>
              <p className="lp-bubble is-user">Foi pagamento de um cliente.</p>
              <p className="lp-bubble is-app">
                Obrigado. Registrei essa movimentação como pagamento de cliente. Ela pode ter
                relevância fiscal e aparece no seu parecer.
              </p>
            </div>
          </div>

          <div className="lp-show-stack">
            <div className="lp-show-panel lp-reveal">
              <div className="lp-show-panel-head">
                <h3>Resumo do painel</h3>
                <IllustrativeTag />
              </div>
              <div className="lp-summary">
                <div>
                  <small>Organizadas</small>
                  <strong>42</strong>
                </div>
                <div>
                  <small>Para revisar</small>
                  <strong>3</strong>
                </div>
                <div>
                  <small>Alertas</small>
                  <strong>2</strong>
                </div>
              </div>
            </div>

            <div className="lp-show-panel lp-reveal">
              <div className="lp-show-panel-head">
                <h3>Alertas</h3>
                <IllustrativeTag />
              </div>
              <ul className="lp-alert-list">
                <li className="lp-alert-item">
                  <Bell size={16} aria-hidden="true" />
                  Há movimentações aguardando sua confirmação.
                </li>
                <li className="lp-alert-item">
                  <Bell size={16} aria-hidden="true" />
                  Uma entrada recente pode ter relevância fiscal. Confira os detalhes.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
