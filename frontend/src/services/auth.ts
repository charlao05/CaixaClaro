import { api } from './api'

export type Regime = 'MEI' | 'SIMPLES' | 'PF'

export type Usuario = {
  id: string
  email: string
  nome: string | null
  regime: Regime
}

export type AuthResponse = {
  token: string
  expires_at: string
  user: Usuario
}

export type LoginResponse = AuthResponse
export type RegisterResponse = AuthResponse

export function register(
  email: string,
  senha: string,
  cpf: string,
): Promise<RegisterResponse> {
  return api<RegisterResponse>('/auth/register', {
    method: 'POST',
    body: {
      email,
      senha,
      cpf,
    },
  })
}

export function login(
  email: string,
  senha: string,
): Promise<LoginResponse> {
  return api<LoginResponse>('/auth/login', {
    method: 'POST',
    body: {
      email,
      senha,
    },
  })
}

export function logout(token: string): Promise<void> {
  return api<{ ok: true }>('/auth/logout', {
    method: 'POST',
    token,
  }).then(() => undefined)
}
