import { ArrowDownLeft, ArrowLeftRight, Info, Sprout, User } from 'lucide-react'

/* DADO ILUSTRATIVO: todas as movimentações abaixo são fictícias, apenas para demonstrar a interface. */
export default function PhoneMockup() {
  return (
    <>
      <div
        className="lp-phone"
        role="img"
        aria-label="Exemplo ilustrativo do aplicativo CaixaClaro mostrando três movimentações: um Pix recebido que precisa de confirmação, uma transferência e um rendimento."
      >
        <div className="lp-phone-screen" aria-hidden="true">
          <div className="lp-phone-status">
            <span>9:41</span>
            <span className="lp-phone-notch" />
            <span>100%</span>
          </div>

          <div className="lp-phone-title">
            <div>
              <small>Movimentações de hoje</small>
              <strong>O que aconteceu</strong>
            </div>
            <span className="lp-phone-avatar">
              <User size={16} />
            </span>
          </div>

          <article className="lp-tx-card is-ask">
            <div className="lp-tx-top">
              <span className="lp-tx-icon is-amber">
                <ArrowDownLeft size={18} />
              </span>
              <div className="lp-tx-label">
                <strong>PIX recebido</strong>
                <span>Hoje, 10:12</span>
              </div>
              <span className="lp-tx-value">R$ 650,00</span>
            </div>
            <span className="lp-tx-status is-ask">
              <Info size={12} />
              Precisa de contexto
            </span>
            <p className="lp-tx-note">
              O CaixaClaro precisa de mais contexto para entender esta movimentação.
            </p>
            <span className="lp-tx-action">Confirmar origem</span>
          </article>

          <article className="lp-tx-card">
            <div className="lp-tx-top">
              <span className="lp-tx-icon is-blue">
                <ArrowLeftRight size={18} />
              </span>
              <div className="lp-tx-label">
                <strong>Transferência</strong>
                <span>Ontem, 18:40</span>
              </div>
              <span className="lp-tx-value">R$ 1.200,00</span>
            </div>
            <p className="lp-tx-note">
              Esta movimentação pode representar apenas uma transferência entre contas.
            </p>
          </article>

          <article className="lp-tx-card">
            <div className="lp-tx-top">
              <span className="lp-tx-icon is-mint">
                <Sprout size={18} />
              </span>
              <div className="lp-tx-label">
                <strong>Rendimento</strong>
                <span>Ontem, 06:00</span>
              </div>
              <span className="lp-tx-value">R$ 38,50</span>
            </div>
            <p className="lp-tx-note">
              Foi identificado um rendimento. Confira os detalhes da movimentação.
            </p>
          </article>
        </div>
      </div>
      <p className="lp-illustrative">
        <Info size={13} aria-hidden="true" />
        Exemplos ilustrativos
      </p>
    </>
  )
}
