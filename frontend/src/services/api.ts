export type ApiErrorBody = {
  erro: string
  mensagem: string
}

export class ApiError extends Error {
  readonly status: number
  readonly codigo: string
  readonly retryAfter: string | null

  constructor(
    status: number,
    body: ApiErrorBody,
    retryAfter: string | null,
  ) {
    super(body.mensagem)
    this.name = 'ApiError'
    this.status = status
    this.codigo = body.erro
    this.retryAfter = retryAfter
  }
}

type RequestOptions = Omit<RequestInit, 'body' | 'headers'> & {
  body?: unknown
  token?: string | null
  headers?: HeadersInit
  idempotencyKey?: string
}

const API_BASE = '/api/v1'

function extrairErro(status: number, payload: unknown): ApiErrorBody {
  const fallback: ApiErrorBody = {
    erro: `HTTP_${status}`,
    mensagem: 'Erro ao comunicar com a API.',
  }

  if (!payload || typeof payload !== 'object') return fallback

  const obj = payload as {
    detail?: unknown
    erro?: unknown
    mensagem?: unknown
  }

  // FastAPI com exception handler: corpo flat { erro, mensagem }
  if (typeof obj.erro === 'string' && typeof obj.mensagem === 'string') {
    return { erro: obj.erro, mensagem: obj.mensagem }
  }

  const detail = obj.detail

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { erro?: unknown; mensagem?: unknown }
    return {
      erro: typeof d.erro === 'string' ? d.erro : fallback.erro,
      mensagem: typeof d.mensagem === 'string' ? d.mensagem : fallback.mensagem,
    }
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const primeiro = detail[0] as { msg?: unknown }
    return {
      erro: 'VALIDACAO',
      mensagem:
        typeof primeiro?.msg === 'string'
          ? primeiro.msg
          : fallback.mensagem,
    }
  }

  if (typeof detail === 'string') {
    return { erro: fallback.erro, mensagem: detail }
  }

  return fallback
}

export async function api<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, token, headers, idempotencyKey, ...requestInit } = options

  const requestHeaders = new Headers(headers)

  if (body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  if (token) {
    requestHeaders.set('Authorization', `Bearer ${token}`)
  }

  if (idempotencyKey) {
    requestHeaders.set('Idempotency-Key', idempotencyKey)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...requestInit,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extrairErro(response.status, payload),
      response.headers.get('Retry-After'),
    )
  }

  return payload as T
}

export type Paginado<T> = {
  itens: T[]
  next_cursor: string | null
  has_more: boolean
}