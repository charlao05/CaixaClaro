"""Cliente Pluggy — M3b (conexao).

Escopo minimo: obter API key e criar connect token.
Sem cache, sem retry, sem persistencia local do token.

Contrato: docs/CONTRATO_API.md secao "Conexao (M3b)".
"""
import httpx

from ..config import settings
from ..security.erros import erro


def _credenciais() -> tuple[str, str, str]:
    s = settings()
    if not s.pluggy_client_id or not s.pluggy_client_secret:
        raise erro(
            503,
            "PLUGGY_NAO_CONFIGURADO",
            "Credenciais Pluggy ausentes no ambiente.",
        )
    return s.pluggy_client_id, s.pluggy_client_secret, s.pluggy_base_url


async def _obter_api_key(client: httpx.AsyncClient) -> str:
    cid, csecret, _ = _credenciais()
    r = await client.post(
        "/auth",
        json={"clientId": cid, "clientSecret": csecret},
    )
    if r.status_code != 200:
        raise erro(502, "PLUGGY_AUTH_FALHOU", "Falha ao autenticar na Pluggy.")
    return r.json()["apiKey"]


async def criar_connect_token(user_id) -> dict:
    """Cria connect token Pluggy com clientUserId = user_id.

    Retorna {"connect_token": str, "expira_em": str | None}.
    """
    _, _, base = _credenciais()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        api_key = await _obter_api_key(client)
        r = await client.post(
            "/connect_token",
            headers={"X-API-KEY": api_key},
            json={"options": {"clientUserId": str(user_id)}},
        )
        if r.status_code not in (200, 201):
            raise erro(
                502,
                "PLUGGY_CONNECT_TOKEN_FALHOU",
                "Falha ao criar connect token na Pluggy.",
            )
        data = r.json()
        return {
            "connect_token": data["accessToken"],
            "expira_em": data.get("expiresAt"),
        }
async def buscar_item(item_id: str) -> dict:
    """GET /items/{item_id}. Retorna o JSON do Item."""
    _, _, base = _credenciais()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        api_key = await _obter_api_key(client)
        r = await client.get(
            f"/items/{item_id}",
            headers={"X-API-KEY": api_key},
        )
        if r.status_code != 200:
            raise erro(
                502,
                "PLUGGY_ITEM_FALHOU",
                "Falha ao buscar Item na Pluggy.",
            )
        return r.json()


async def listar_accounts(item_id: str) -> list:
    """GET /accounts?itemId={item_id}. Retorna a lista de contas."""
    _, _, base = _credenciais()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        api_key = await _obter_api_key(client)
        r = await client.get(
            "/accounts",
            params={"itemId": item_id},
            headers={"X-API-KEY": api_key},
        )
        if r.status_code != 200:
            raise erro(
                502,
                "PLUGGY_ACCOUNTS_FALHOU",
                "Falha ao listar contas na Pluggy.",
            )
        return r.json()["results"]



async def listar_transactions(
    account_id: str, cursor: str | None = None
) -> dict:
    """GET /v2/transactions?accountId={id}. Paginacao por cursor.

    Retorna {results, next}. 'next' e o cursor da proxima pagina ou None.
    """
    _, _, base = _credenciais()
    params = {"accountId": account_id}
    if cursor:
        params["after"] = cursor

    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
        api_key = await _obter_api_key(client)
        r = await client.get(
            "/v2/transactions",
            params=params,
            headers={"X-API-KEY": api_key},
        )
        if r.status_code != 200:
            raise erro(
                502,
                "PLUGGY_TRANSACTIONS_FALHOU",
                f"Falha ao listar transações na Pluggy: {r.status_code}",
            )
        return r.json()
async def revogar_item(item_id: str) -> None:
    """DELETE /items/{item_id}. Revoga Item e consent na Pluggy.

    Idempotente do lado Pluggy: 404 e tratado como sucesso, porque o
    estado desejado (item inexistente) ja esta satisfeito.
    """
    _, _, base = _credenciais()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        api_key = await _obter_api_key(client)
        r = await client.delete(
            f"/items/{item_id}",
            headers={"X-API-KEY": api_key},
        )
        if r.status_code in (200, 204, 404):
            return
        raise erro(
            502,
            "PLUGGY_REVOGAR_FALHOU",
            "Falha ao revogar Item na Pluggy.",
        )





async def registrar_webhook_pluggy(url: str, secret: str) -> dict:
    """Registra webhook de aplicacao na Pluggy com header customizado."""
    _, _, base = _credenciais()
    async with httpx.AsyncClient(base_url=base, timeout=20) as client:
        api_key = await _obter_api_key(client)
        r = await client.post(
            f"{base}/webhooks",
            headers={"X-API-KEY": api_key},
            json={
                "url": url,
                "event": "all",
                "headers": {"X-CaixaClaro-Webhook-Secret": secret},
            },
        )
        if r.status_code not in (200, 201):
            raise erro(
                502,
                "PLUGGY_WEBHOOK_FALHOU",
                f"Falha ao registrar webhook: {r.status_code} {r.text[:200]}",
            )
        return r.json()
