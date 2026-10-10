"""IP do cliente atrás do Caddy e do Cloudflare Tunnel.

Revisão de 2026-10-09, achado R10. Cadeia em produção
(docs/M10_DECISAO_2026-08.md, docker-compose.prod.yml):

    cliente → borda da Cloudflare → cloudflared no VPS → Caddy (web) → api:8000

A API só enxerga o Caddy: `request.client.host` é o endereço do contêiner
`web` para todas as requisições. Como o limite de tentativas usa o IP como
chave, ele tratava todos os usuários como um só (5 cadastros por hora no
produto inteiro, 10 senhas erradas de qualquer pessoa bloqueando o login de
todos).

Regra:

  1. A API só aceita os cabeçalhos abaixo quando a conexão dela vem de um
     endereço interno (o Caddy, na rede do compose). Se um dia a API for
     exposta direto, os cabeçalhos passam a ser ignorados.
  2. `X-CaixaClaro-Conexao` é escrito pelo Caddy (Caddyfile, `header_up`,
     que substitui qualquer valor enviado pelo cliente) com o endereço de
     quem abriu a conexão com ele.
       - Endereço interno: a conexão veio de dentro do servidor, isto é, do
         conector do Tunnel. Vale `CF-Connecting-IP`, que a borda da
         Cloudflare preenche com o IP de quem acessou o site.
       - Endereço público: alguém acessou o servidor direto, sem passar
         pela Cloudflare. Vale esse endereço; `CF-Connecting-IP`, que esse
         cliente poderia forjar, é ignorado.
  3. Sem o cabeçalho do Caddy (desenvolvimento, testes): comportamento
     antigo, `request.client.host`.
"""
import ipaddress

from fastapi import Request

CABECALHO_CONEXAO = "x-caixaclaro-conexao"
CABECALHO_CLOUDFLARE = "cf-connecting-ip"

# "Interno" = dentro do servidor ou da rede do compose. Lista explícita: o
# `is_private` do Python também classifica como privados alguns blocos
# reservados que não têm nada a ver com isso (os de documentação, por
# exemplo).
_REDES_INTERNAS = tuple(
    ipaddress.ip_network(rede)
    for rede in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _ip(valor: str | None) -> str | None:
    """Primeiro endereço de um cabeçalho, normalizado; None se não for IP."""
    if not valor:
        return None
    candidato = valor.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return None


def _interno(ip: str | None) -> bool:
    if ip is None:
        return False
    endereco = ipaddress.ip_address(ip)
    if isinstance(endereco, ipaddress.IPv6Address) and endereco.ipv4_mapped:
        endereco = endereco.ipv4_mapped
    return any(endereco in rede for rede in _REDES_INTERNAS)


def ip_do_cliente(request: Request) -> str:
    """IP de quem fez a requisição, para limite de tentativas e auditoria."""
    direto = request.client.host if request.client else None
    if not _interno(_ip(direto)):
        return direto or "desconhecido"

    conexao = _ip(request.headers.get(CABECALHO_CONEXAO))
    if conexao is None:
        return direto or "desconhecido"

    if _interno(conexao):
        return _ip(request.headers.get(CABECALHO_CLOUDFLARE)) or conexao
    return conexao
