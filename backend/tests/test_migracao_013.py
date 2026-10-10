"""Migration 013 — backfill das confirmações gravadas antes do M13.

Até o M13, trocar a categoria ao confirmar deixava propósito, patrimônio e
tratamento presos ao palpite original; por isso a entrada confirmada como
trabalho não contava no faturamento. A migration alinha o que já estava
gravado com a regra que o código aplica hoje (`dimensoes_padrao`).
"""
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from caixaclaro.db import conexao
from caixaclaro.domain.fiscal.classificacao import dimensoes_padrao
from caixaclaro.domain.fiscal.taxonomia import CATEGORIAS
from caixaclaro.services.faturamento import somar_faturamento_do_ano

ANO = date.today().year
MIGRATION = Path(__file__).parent.parent / "migrations" / "013_faturamento_por_ano.sql"


def _backfill_sql() -> str:
    comandos = [c.strip() for c in MIGRATION.read_text(encoding="utf-8").split(";")]
    (update,) = [c for c in comandos if "UPDATE transactions AS t" in c]
    return update


async def _registrar(client) -> uuid.UUID:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "m013@x.com", "senha": "senha12345", "cpf": "444.444.440-10"},
    )
    assert r.status_code == 201, r.json()
    return uuid.UUID(r.json()["user"]["id"])


async def _inserir(conn, uid, descricao, *, categoria, original, proposito, patrimonio,
                   tratamento, via, confirmada, valor="100.00"):
    return await conn.fetchval(
        """
        INSERT INTO transactions
          (user_id, origem, data, descricao_bruta, valor, categoria,
           categoria_original, proposito, patrimonio, tratamento_tributario,
           via, needs_review, confirmado_por, confirmado_em)
        VALUES ($1, 'manual', $2, $3, $4, $5, $6, $7, $8, $9, $10, false,
                $11, CASE WHEN $11::uuid IS NULL THEN NULL ELSE now() END)
        RETURNING id
        """,
        uid, date(ANO, 3, 10), descricao, Decimal(valor), categoria, original,
        proposito, patrimonio, tratamento, via, uid if confirmada else None,
    )


async def _dims(conn, tx_id):
    r = await conn.fetchrow(
        "SELECT proposito, patrimonio, tratamento_tributario, via "
        "FROM transactions WHERE id = $1",
        tx_id,
    )
    return r["proposito"], r["patrimonio"], r["tratamento_tributario"], r["via"]


async def test_backfill_alinha_toda_categoria_com_a_regra_do_codigo(client):
    uid = await _registrar(client)
    async with conexao() as conn:
        ids = {}
        for categoria in CATEGORIAS:
            original = "outros" if categoria != "outros" else "receita_servico"
            # Dimensões do palpite ORIGINAL, como o main deixava gravado.
            prop, _origem, patr, trat = dimensoes_padrao(original)
            ids[categoria] = await _inserir(
                conn, uid, f"confirmada como {categoria}",
                categoria=categoria, original=original, proposito=prop,
                patrimonio=patr, tratamento=trat, via="heuristica", confirmada=True,
            )

        await conn.execute(_backfill_sql())

        for categoria, tx_id in ids.items():
            prop, _origem, patr, trat = dimensoes_padrao(categoria)
            assert await _dims(conn, tx_id) == (prop, patr, trat, "usuario"), categoria


async def test_backfill_faz_a_confirmacao_antiga_contar_no_faturamento(client):
    uid = await _registrar(client)
    async with conexao() as conn:
        await _inserir(
            conn, uid, "PIX RECEBIDO JOAO SILVA",
            categoria="receita_servico", original="outros",
            proposito="outros_indeterminado", patrimonio="pessoa_fisica",
            tratamento="indeterminado_pendente", via="heuristica",
            confirmada=True, valor="750.00",
        )
        assert await somar_faturamento_do_ano(conn, uid, ANO) == Decimal("0")
        await conn.execute(_backfill_sql())
        assert await somar_faturamento_do_ano(conn, uid, ANO) == Decimal("750.00")


async def test_backfill_nao_toca_no_que_nao_precisa(client):
    uid = await _registrar(client)
    async with conexao() as conn:
        casos = {
            # O usuário aceitou a categoria da máquina: as dimensões já batem,
            # inclusive um propósito mais específico que o padrão.
            "aceitou_o_palpite": dict(
                categoria="outros", original="outros", proposito="aporte_capital",
                patrimonio="ponte_pf_pj", tratamento="isento_nao_tributavel",
                via="heuristica", confirmada=True,
            ),
            # Ainda não confirmada.
            "nao_confirmada": dict(
                categoria="outros", original="outros",
                proposito="outros_indeterminado", patrimonio="pessoa_fisica",
                tratamento="indeterminado_pendente", via="heuristica",
                confirmada=False,
            ),
            # Decisão gravada já pelo código novo, com propósito escolhido.
            "decisao_do_m13": dict(
                categoria="pessoal_prolabore", original="custo_operacional",
                proposito="gasto_pessoal", patrimonio="ponte_pf_pj",
                tratamento="indeterminado_pendente", via="usuario",
                confirmada=True,
            ),
        }
        ids = {
            nome: await _inserir(conn, uid, nome, **campos)
            for nome, campos in casos.items()
        }
        antes = {nome: await _dims(conn, tx_id) for nome, tx_id in ids.items()}

        await conn.execute(_backfill_sql())

        depois = {nome: await _dims(conn, tx_id) for nome, tx_id in ids.items()}
    assert depois == antes


async def test_backfill_pode_rodar_de_novo_sem_mudar_nada(client):
    uid = await _registrar(client)
    async with conexao() as conn:
        tx_id = await _inserir(
            conn, uid, "PIX RECEBIDO JOAO SILVA",
            categoria="receita_servico", original="outros",
            proposito="outros_indeterminado", patrimonio="pessoa_fisica",
            tratamento="indeterminado_pendente", via="heuristica", confirmada=True,
        )
        primeira = await conn.execute(_backfill_sql())
        dims = await _dims(conn, tx_id)
        segunda = await conn.execute(_backfill_sql())
        assert primeira == "UPDATE 1"
        assert segunda == "UPDATE 0"
        assert await _dims(conn, tx_id) == dims
