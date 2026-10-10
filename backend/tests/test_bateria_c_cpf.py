"""O roteiro da prova real com a Pluggy (scripts/bateria_c.py, critério do
M3b) gera CPFs que o cadastro aceita.

Antes desta correção ele gerava só CPFs de dígitos repetidos
("111.111.111-11"), recusados pelo cadastro desde 2026-09-30.
"""
from caixaclaro.security.validacao import validar_cpf
from scripts.bateria_c import _cpf_sintetico


def test_cpfs_gerados_sao_validos_e_variados():
    gerados = {_cpf_sintetico() for _ in range(300)}
    assert all(validar_cpf(c) for c in gerados)
    assert len(gerados) > 250
