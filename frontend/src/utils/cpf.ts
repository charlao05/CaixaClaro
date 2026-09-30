/** Utilitarios de CPF. Espelha backend/src/caixaclaro/security/validacao.py. */

export function apenasDigitos(input: string): string {
  return input.replace(/\D/g, '').slice(0, 11)
}

export function formatarCPF(input: string): string {
  const d = apenasDigitos(input)
  if (d.length <= 3) return d
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
}

export function validarCPF(input: string): boolean {
  const digitos = apenasDigitos(input)
  if (digitos.length !== 11) return false
  if (digitos === digitos[0].repeat(11)) return false

  let soma = 0
  for (let i = 0; i < 9; i++) {
    soma += Number(digitos[i]) * (10 - i)
  }
  let resto = soma % 11
  const dv1 = resto < 2 ? 0 : 11 - resto
  if (Number(digitos[9]) !== dv1) return false

  soma = 0
  for (let i = 0; i < 10; i++) {
    soma += Number(digitos[i]) * (11 - i)
  }
  resto = soma % 11
  const dv2 = resto < 2 ? 0 : 11 - resto
  return Number(digitos[10]) === dv2
}
