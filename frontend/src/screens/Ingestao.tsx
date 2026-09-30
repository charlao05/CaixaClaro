import { useState, type ChangeEvent, type FormEvent } from 'react'
import { ApiError } from '../services/api'
import type { Sessao } from '../services/session'
import {
  colar,
  importar,
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
          {t.data} — {t.descricao_bruta} — {formatBRL(t.valor)} ({t.origem})
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
        <h2>Colar extrato</h2>
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
          </div>
        )}
      </section>

      <section>
        <h2>Importar arquivo de extrato</h2>
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
          </div>
        )}
      </section>
    </main>
  )
}