import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  anotar,
  colar,
  getOpcoesResposta,
  importar,
  type OpcoesResposta,
  type ColarResponse,
  type ImportarResponse,
  type FormatoArquivo,
  type TransacaoResumo,
} from '../services/transacoes'

type Props = {
  sessao: Sessao
  onVoltar: () => void
}

function formatBRL(s: string): string {
  const n = parseFloat(s)
  if (!isFinite(n)) return s
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatData(iso: string): string {
  const partes = iso.slice(0, 10).split('-')
  if (partes.length !== 3) return iso
  return `${partes[2]}/${partes[1]}/${partes[0]}`
}

function hojeISO(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// "50", "50,00", "1.250,90" ou "50.00" -> "50.00". null se não for um valor.
function normalizarValor(bruto: string): string | null {
  let v = bruto.trim().replace(/^R\$\s*/i, '')
  if (v.includes(',')) v = v.replace(/\./g, '').replace(',', '.')
  if (!/^\d+(\.\d{1,2})?$/.test(v)) return null
  if (parseFloat(v) === 0) return null
  return v
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('Falha ao ler arquivo.'))
        return
      }
      const comma = result.indexOf(',')
      if (comma < 0) {
        reject(new Error('Falha ao ler arquivo.'))
        return
      }
      resolve(result.slice(comma + 1))
    }
    reader.onerror = () => {
      reject(reader.error ?? new Error('Falha ao ler arquivo.'))
    }
    reader.readAsDataURL(file)
  })
}

function Resultado({ itens }: { itens: TransacaoResumo[] }) {
  if (itens.length === 0) return <p>Nenhum lançamento importado.</p>
  return (
    <ul>
      {itens.map((t) => (
        <li key={t.id}>
          {formatData(t.data)} — {t.descricao_bruta} — {formatBRL(t.valor)}
        </li>
      ))}
    </ul>
  )
}

function msgErro(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter
      ? `${e.message} Tente novamente em ${e.retryAfter}s.`
      : e.message
  }
  return 'Erro inesperado.'
}

export default function Ingestao({ sessao, onVoltar }: Props) {
  const [texto, setTexto] = useState('')
  const [colando, setColando] = useState(false)
  const [erroColar, setErroColar] = useState<string | null>(null)
  const [resColar, setResColar] = useState<ColarResponse | null>(null)

  const [arquivo, setArquivo] = useState<File | null>(null)
  const [formato, setFormato] = useState<FormatoArquivo>('csv')
  const [importando, setImportando] = useState(false)
  const [erroImportar, setErroImportar] = useState<string | null>(null)
  const [resImportar, setResImportar] = useState<ImportarResponse | null>(null)

  const [opcoes, setOpcoes] = useState<OpcoesResposta | null>(null)
  const [direcao, setDirecao] = useState<'entrou' | 'saiu'>('entrou')
  const [dataManual, setDataManual] = useState(() => hojeISO())
  const [descManual, setDescManual] = useState('')
  const [valorManual, setValorManual] = useState('')
  const [opcaoId, setOpcaoId] = useState('')
  const [anotando, setAnotando] = useState(false)
  const [erroAnotar, setErroAnotar] = useState<string | null>(null)
  const [okAnotar, setOkAnotar] = useState<string | null>(null)

  useEffect(() => {
    let ativo = true
    getOpcoesResposta(sessao.token)
      .then((o) => {
        if (ativo) setOpcoes(o)
      })
      .catch(() => {
        // sem as opções o formulário continua funcionando: o lançamento
        // vai para a revisão e a pergunta é feita lá.
      })
    return () => {
      ativo = false
    }
  }, [sessao.token])

  const opcoesDaDirecao = opcoes
    ? direcao === 'entrou'
      ? opcoes.entrada
      : opcoes.saida
    : []

  async function handleAnotar(e: FormEvent) {
    e.preventDefault()
    setErroAnotar(null)
    setOkAnotar(null)
    const valor = normalizarValor(valorManual)
    if (!valor) {
      setErroAnotar('Escreva o valor assim: 50,00')
      return
    }
    const escolhida = opcoesDaDirecao.find((o) => o.id === opcaoId)
    setAnotando(true)
    try {
      const t = await anotar(sessao.token, {
        data: dataManual,
        descricao: descManual.trim(),
        valor: direcao === 'saiu' ? `-${valor}` : valor,
        ...(escolhida
          ? { categoria: escolhida.categoria, proposito: escolhida.proposito }
          : {}),
      })
      setOkAnotar(
        t.needs_review
          ? 'Anotado. Como você não disse o que foi, ele ficou esperando a sua resposta na revisão.'
          : `Anotado: ${t.rotulo}.`,
      )
      setDescManual('')
      setValorManual('')
      setOpcaoId('')
    } catch (e) {
      setErroAnotar(msgErro(e))
    } finally {
      setAnotando(false)
    }
  }

  async function handleColar(e: FormEvent) {
    e.preventDefault()
    setErroColar(null)
    setResColar(null)
    setColando(true)
    try {
      const r = await colar(sessao.token, texto)
      setResColar(r)
    } catch (e) {
      setErroColar(msgErro(e))
    } finally {
      setColando(false)
    }
  }

  function handleArquivo(e: ChangeEvent<HTMLInputElement>) {
    setArquivo(e.target.files?.[0] ?? null)
    setResImportar(null)
    setErroImportar(null)
  }

  async function handleImportar(e: FormEvent) {
    e.preventDefault()
    if (!arquivo) return
    setErroImportar(null)
    setResImportar(null)
    setImportando(true)
    try {
      const b64 = await fileToBase64(arquivo)
      const r = await importar(sessao.token, formato, b64)
      setResImportar(r)
    } catch (e) {
      setErroImportar(msgErro(e))
    } finally {
      setImportando(false)
    }
  }

  return (
    <main className="dashboard">
      <header>
        <h1>CaixaClaro</h1>
        <div>
          <span>{sessao.user.email}</span>
          <button type="button" onClick={onVoltar}>
            Voltar ao painel
          </button>
        </div>
      </header>

      <section>
        <h2>Anotar um recebimento ou gasto</h2>
        <p className="assinatura-nota">
          Para quem recebe em dinheiro ou ainda não tem extrato organizado.
          Um lançamento por vez.
        </p>
        <form onSubmit={handleAnotar}>
          <fieldset className="assinatura-metodo">
            <legend>O dinheiro</legend>
            <label>
              <input
                type="radio"
                name="direcao"
                checked={direcao === 'entrou'}
                onChange={() => {
                  setDirecao('entrou')
                  setOpcaoId('')
                }}
                disabled={anotando}
              />
              Entrou
            </label>
            <label>
              <input
                type="radio"
                name="direcao"
                checked={direcao === 'saiu'}
                onChange={() => {
                  setDirecao('saiu')
                  setOpcaoId('')
                }}
                disabled={anotando}
              />
              Saiu
            </label>
          </fieldset>
          <label>
            Quando
            <input
              type="date"
              value={dataManual}
              max={hojeISO()}
              onChange={(e) => setDataManual(e.target.value)}
              required
              disabled={anotando}
            />
          </label>
          <label>
            Quanto
            <input
              type="text"
              inputMode="decimal"
              placeholder="50,00"
              value={valorManual}
              onChange={(e) => setValorManual(e.target.value)}
              required
              disabled={anotando}
            />
          </label>
          <label>
            Uma descrição para você lembrar
            <input
              type="text"
              placeholder={direcao === 'entrou' ? 'Ex.: corte de cabelo da Ana' : 'Ex.: gasolina'}
              value={descManual}
              onChange={(e) => setDescManual(e.target.value)}
              maxLength={200}
              required
              disabled={anotando}
            />
          </label>
          <label>
            O que foi?
            <select
              value={opcaoId}
              onChange={(e) => setOpcaoId(e.target.value)}
              disabled={anotando}
            >
              <option value="">Não sei agora (respondo depois)</option>
              {opcoesDaDirecao.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {erroAnotar && <p role="alert">{erroAnotar}</p>}
          {okAnotar && (
            <p role="status" className="perfil-ok">
              {okAnotar}
            </p>
          )}
          <button
            type="submit"
            disabled={anotando || descManual.trim().length === 0}
          >
            {anotando ? 'Anotando...' : 'Anotar'}
          </button>
        </form>
      </section>

      <section>
        <h2>Colar extrato</h2>
        <p className="assinatura-nota">
          Copie as linhas do extrato no site ou no aplicativo do seu banco e
          cole aqui. Cada lançamento precisa ter data, descrição e valor.
        </p>
        <form onSubmit={handleColar}>
          <label>
            Texto do extrato
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              required
              rows={8}
              disabled={colando}
            />
          </label>
          {erroColar && <p role="alert">{erroColar}</p>}
          <button
            type="submit"
            disabled={colando || texto.trim().length === 0}
          >
            {colando ? 'Enviando...' : 'Enviar extrato'}
          </button>
        </form>
        {resColar && (
          <div>
            <p>{resColar.importados === 1 ? '1 lançamento importado.' : `${resColar.importados} lançamentos importados.`}</p>
            <Resultado itens={resColar.itens} />
            <button type="button" onClick={onVoltar}>
              Ver o que precisa da minha resposta
            </button>
          </div>
        )}
      </section>

      <section>
        <h2>Importar arquivo de extrato</h2>
        <p className="assinatura-nota">
          No site ou aplicativo do banco, procure a opção de exportar o
          extrato em CSV ou OFX e envie o arquivo aqui.
        </p>
        <form onSubmit={handleImportar}>
          <label>
            Formato
            <select
              value={formato}
              onChange={(e) => setFormato(e.target.value as FormatoArquivo)}
              disabled={importando}
            >
              <option value="csv">CSV (planilha)</option>
              <option value="ofx">OFX (extrato bancário)</option>
            </select>
          </label>
          <label>
            Arquivo
            <input
              type="file"
              accept=".csv,.ofx,text/csv"
              onChange={handleArquivo}
              disabled={importando}
            />
          </label>
          {erroImportar && <p role="alert">{erroImportar}</p>}
          <button type="submit" disabled={importando || !arquivo}>
            {importando ? 'Importando...' : 'Importar arquivo'}
          </button>
        </form>
        {resImportar && (
          <div>
            <p>{resImportar.importados === 1 ? '1 lançamento importado.' : `${resImportar.importados} lançamentos importados.`}</p>
            <Resultado itens={resImportar.itens} />
            <button type="button" onClick={onVoltar}>
              Ver o que precisa da minha resposta
            </button>
          </div>
        )}
      </section>
    </main>
  )
}