import base64
from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8")
    ambiente: Literal["dev","staging","prod"]="dev"
    database_url:str
    jwt_secret:str
    jwt_expira_minutos:int=60
    cpf_hmac_key:str
    cpf_aes_key:str
    pluggy_client_id:str|None=None
    pluggy_client_secret:str|None=None
    pluggy_base_url:str='https://api.pluggy.ai'
    asaas_api_key:str|None=None
    telegram_bot_token:str|None=None
    asaas_base_url:str='https://api.asaas.com/v3'
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
