/**
 * Sessao do usuario.
 *
 * Armazenamento: sessionStorage.
 *   - sobrevive a reload da aba;
 *   - nao sobrevive a fechar o browser;
 *   - trade-off aceito: nao ha sincronizacao entre abas.
 *     Abrir o app em outra aba exige login novamente.
 *
 * Alternativas consideradas:
 *   - localStorage: persistiria entre reinicios do browser,
 *     o que e indesejavel para um app financeiro sem refresh token;
 *   - cookie HttpOnly: exigiria mudanca no contrato/backend
 *     (hoje a autenticacao e via Authorization: Bearer).
 *
 * Este modulo NAO decodifica JWT. A expiracao e lida a partir de
 * `expiresAt`, que vem do backend em /auth/login e /auth/register.
 *
 * Nenhum outro modulo acessa sessionStorage diretamente.
 */
import type { Usuario } from './auth'

export type Sessao = {
  token: string
  expiresAt: string
  user: Usuario
}

const CHAVE = 'caixaclaro.sessao'

export function salvarSessao(s: Sessao): void {
  sessionStorage.setItem(CHAVE, JSON.stringify(s))
}

export function limparSessao(): void {
  sessionStorage.removeItem(CHAVE)
}

export function sessaoExpirada(s: Sessao): boolean {
  const t = Date.parse(s.expiresAt)
  if (Number.isNaN(t)) return true
  return t <= Date.now()
}

export function carregarSessao(): Sessao | null {
  const raw = sessionStorage.getItem(CHAVE)
  if (!raw) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    limparSessao()
    return null
  }

  if (!parsed || typeof parsed !== 'object') {
    limparSessao()
    return null
  }

  const s = parsed as Partial<Sessao>
  if (typeof s.token !== 'string' || typeof s.expiresAt !== 'string' || !s.user) {
    limparSessao()
    return null
  }

  const sessao: Sessao = {
    token: s.token,
    expiresAt: s.expiresAt,
    user: s.user,
  }

  if (sessaoExpirada(sessao)) {
    limparSessao()
    return null
  }

  return sessao
}