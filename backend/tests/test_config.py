from pathlib import Path

import pytest
from pydantic import ValidationError

from caixaclaro.config import Settings


def test_env_example_tem_todos_os_campos_de_settings():
    raiz = Path(__file__).parents[1]
    env_exemplo = raiz / ".env.example"

    nomes = set()
    for linha in env_exemplo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome = linha.split("=", 1)[0].strip()
        nomes.add(nome)

    esperados = {nome.upper() for nome in Settings.model_fields}
    assert nomes == esperados


def test_repr_e_str_nao_expoem_segredos():
    segredos = {
        "postgresql://user:senha@db:5432/caixaclaro",
        "jwt-secreto-de-teste-com-mais-de-trinta-dois-caracteres",
        "hmac-secreto-de-teste",
        "aes-secreto-de-teste",
        "pluggy-secret",
        "asaas-secret",
        "telegram-secret",
        "pluggy-webhook-secret",
        "asaas-webhook-secret",
        "telegram-webhook-secret",
    }

    settings = Settings(
        ambiente="dev",
        database_url="postgresql://user:senha@db:5432/caixaclaro",
        jwt_secret="jwt-secreto-de-teste-com-mais-de-trinta-dois-caracteres",
        cpf_hmac_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        cpf_aes_key="ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA=",
        pluggy_client_id="pluggy-id",
        pluggy_client_secret="pluggy-secret",
        asaas_api_key="asaas-secret",
        telegram_bot_token="telegram-secret",
        frontend_url="http://localhost:5173",
        pluggy_webhook_secret="pluggy-webhook-secret",
        asaas_webhook_token="asaas-webhook-secret",
        telegram_webhook_secret="telegram-webhook-secret",
    )

    texto = repr(settings)
    texto_str = str(settings)

    for segredo in segredos:
        assert segredo not in texto
        assert segredo not in texto_str

    assert "ambiente='dev'" in texto
    assert "frontend_url_configured=True" in texto
    assert "database_configured=True" in texto
    assert "pluggy_base_url_configured=True" in texto



def test_erro_de_validacao_nao_expoe_valor_invalido():
    valor_invalido = "jwt-invalido-nao-exibir"

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ambiente="dev",
            database_url="postgresql://user:senha@db:5432/caixaclaro",
            jwt_secret=valor_invalido,
            cpf_hmac_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            cpf_aes_key="ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA=",
            frontend_url="http://localhost:5173",
        )

    assert valor_invalido not in str(exc_info.value)
