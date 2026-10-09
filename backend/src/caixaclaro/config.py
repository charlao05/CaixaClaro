import base64
from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", hide_input_in_errors=True)
    ambiente: Literal["dev","staging","prod"]="dev"
    database_url:str
    jwt_secret:str
    jwt_expira_minutos:int=60
    trial_dias:int=7
    cpf_hmac_key:str
    cpf_aes_key:str
    pluggy_client_id:str|None=None
    pluggy_client_secret:str|None=None
    pluggy_base_url:str='https://api.pluggy.ai'
    asaas_api_key:str|None=None
    telegram_bot_token:str|None=None
    asaas_base_url:str='https://api.asaas.com/v3'
    frontend_url:str
    eval_ultima_execucao_path:str="var/eval/ultima_execucao.json"
    pluggy_webhook_secret:str|None=None
    asaas_webhook_token:str|None=None
    telegram_webhook_secret:str|None=None

    def _representacao_segura(self) -> str:
        configurados = (
            f"database_configured={bool(self.database_url)}",
            f"jwt_configured={bool(self.jwt_secret)}",
            f"cpf_hmac_configured={bool(self.cpf_hmac_key)}",
            f"cpf_aes_configured={bool(self.cpf_aes_key)}",
            f"pluggy_configured={bool(self.pluggy_client_id and self.pluggy_client_secret)}",
            f"asaas_configured={bool(self.asaas_api_key)}",
            f"telegram_configured={bool(self.telegram_bot_token)}",
            f"pluggy_webhook_configured={bool(self.pluggy_webhook_secret)}",
            f"asaas_webhook_configured={bool(self.asaas_webhook_token)}",
            f"telegram_webhook_configured={bool(self.telegram_webhook_secret)}",
        )
        seguros = (
            f"ambiente={self.ambiente!r}",
            f"jwt_expira_minutos={self.jwt_expira_minutos}",
            f"trial_dias={self.trial_dias}",
            f"pluggy_base_url_configured={bool(self.pluggy_base_url)}",
            f"asaas_base_url_configured={bool(self.asaas_base_url)}",
            f"frontend_url_configured={bool(self.frontend_url)}",
            f"eval_path_configured={bool(self.eval_ultima_execucao_path)}",
        )
        return f"Settings({', '.join(seguros + configurados)})"

    def __repr__(self) -> str:
        return self._representacao_segura()

    def __str__(self) -> str:
        return self._representacao_segura()

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_minimo(cls,v):
        if v and len(v)<32: raise ValueError("JWT_SECRET precisa ter ao menos 32 caracteres.")
        return v
    @staticmethod
    def _validar_chave_32_b64(v,nome):
        try: decoded=base64.b64decode(v,validate=True)
        except Exception as e: raise ValueError(f"{nome} inválido: {e}")
        if len(decoded)!=32: raise ValueError(f"{nome} precisa decodificar para 32 bytes.")
        return v
    @field_validator("cpf_hmac_key")
    @classmethod
    def cpf_hmac_key_valido(cls,v): return cls._validar_chave_32_b64(v,"CPF_HMAC_KEY")
    @field_validator("cpf_aes_key")
    @classmethod
    def cpf_aes_key_valido(cls,v): return cls._validar_chave_32_b64(v,"CPF_AES_KEY")

@lru_cache
def settings(): return Settings()
