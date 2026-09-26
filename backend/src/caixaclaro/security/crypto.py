import base64,hashlib,hmac,os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ..config import settings
def _chave_hmac(): return base64.b64decode(settings().cpf_hmac_key,validate=True)
def _chave_aes(): return base64.b64decode(settings().cpf_aes_key,validate=True)
def hash_cpf(cpf):
    return hmac.new(_chave_hmac(),"".join(c for c in cpf if c.isdigit()).encode(),hashlib.sha256).hexdigest()
def cifrar_cpf(cpf):
    claro="".join(c for c in cpf if c.isdigit()); nonce=os.urandom(12)
    return nonce+AESGCM(_chave_aes()).encrypt(nonce,claro.encode(),None)
def decifrar_cpf(dados):
    nonce,ct=dados[:12],dados[12:]
    return AESGCM(_chave_aes()).decrypt(nonce,ct,None).decode()
