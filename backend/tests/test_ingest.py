from datetime import date
from decimal import Decimal

import pytest

from caixaclaro.domain.ingest.textnorm import normalizar, calcular_paste_id
from caixaclaro.domain.ingest.valor import parse_valor_bancario
from caixaclaro.domain.ingest.parser_texto import parse_texto, ExtratoIlegivel
from caixaclaro.domain.ingest.parser_csv import parse_csv
from caixaclaro.domain.ingest.parser_ofx import parse_ofx


# ============================================================
# textnorm
# ============================================================

def test_normalizar_colapsa_espacos_acentos_case():
    assert normalizar("  PIX  João\r\n") == "pix joao"


def test_paste_id_estavel_entre_variantes():
    a = calcular_paste_id("  PIX  João\r\n")
    b = calcular_paste_id("PIX JOÃO")
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_paste_id_diferente_para_textos_diferentes():
    assert calcular_paste_id("PIX A") != calcular_paste_id("PIX B")


# ============================================================
# valor
# ============================================================

@pytest.mark.parametrize("entrada,esperado", [
    ("R$ 1.234,56", Decimal("1234.56")),
    ("-50,00", Decimal("-50.00")),
    ("1234.56", Decimal("1234.56")),
    ("1.234,56 D", Decimal("-1234.56")),
    ("1.234,56 C", Decimal("1234.56")),
    ("0,01", Decimal("0.01")),
])
def test_parse_valor_valido(entrada, esperado):
    assert parse_valor_bancario(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    None, "", "   ", "abc", "1e3", "1.2.3,4,5",
])
def test_parse_valor_invalido(entrada):
    assert parse_valor_bancario(entrada) is None


# ============================================================
# parser_texto
# ============================================================

def test_parse_texto_cinco_linhas():
    txt = """25/09 PIX RECEBIDO MARCOS SOUZA R$ 650,00
24/09 CREDITO TED FOLHA PAGTO SALARIO R$ 4.850,00
23/09 ESTORNO COMPRA CANCELADA R$ 389,90
22/09 CREDITO LIBERACAO EMPRESTIMO R$ 12.000,00
21/09 POSTO IPIRANGA COMBUSTIVEL -140,00"""
    out = parse_texto(txt, ano_referencia=2026)
    assert len(out) == 5
    assert out[0].data == date(2026, 9, 25)
    assert out[0].valor == Decimal("650.00")
    assert out[4].valor == Decimal("-140.00")


def test_parse_texto_pula_cabecalho_e_rodape():
    txt = """Extrato Nubank
Saldo disponível: R$ 5.000,00
25/09 PIX RECEBIDO MARCOS R$ 650,00
Total do período: R$ 650,00"""
    out = parse_texto(txt, ano_referencia=2026)
    assert len(out) == 1


def test_parse_texto_vazio_levanta():
    with pytest.raises(ExtratoIlegivel):
        parse_texto("", ano_referencia=2026)


def test_parse_texto_linha_com_data_sem_valor_levanta():
    with pytest.raises(ExtratoIlegivel):
        parse_texto("25/09 PIX SEM VALOR NO FIM", ano_referencia=2026)


# ============================================================
# parser_csv
# ============================================================

def test_parse_csv_com_cabecalho():
    csv_bytes = (
        "data;descricao;valor\n"
        "25/09/2026;PIX RECEBIDO;650,00\n"
        "24/09/2026;POSTO SHELL;-140,00\n"
    ).encode("utf-8")
    out = parse_csv(csv_bytes)
    assert len(out) == 2
    assert out[0].valor == Decimal("650.00")
    assert out[1].valor == Decimal("-140.00")


def test_parse_csv_sem_cabecalho():
    csv_bytes = (
        "25/09/2026;PIX RECEBIDO;650,00\n"
        "24/09/2026;POSTO SHELL;-140,00\n"
    ).encode("utf-8")
    out = parse_csv(csv_bytes)
    assert len(out) == 2


# ============================================================
# parser_ofx
# ============================================================

def test_parse_ofx_dois_lancamentos():
    ofx = """<OFX>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20260925</DTPOSTED>
<TRNAMT>650.00</TRNAMT>
<MEMO>PIX RECEBIDO MARCOS</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20260924</DTPOSTED>
<TRNAMT>-140.00</TRNAMT>
<MEMO>POSTO SHELL</MEMO>
</STMTTRN>
</OFX>""".encode("utf-8")
    out = parse_ofx(ofx)
    assert len(out) == 2
    assert out[0].data == date(2026, 9, 25)
    assert out[0].valor == Decimal("650.00")
    assert out[1].valor == Decimal("-140.00")


def test_parse_ofx_nao_ofx_levanta():
    with pytest.raises(ExtratoIlegivel):
        parse_ofx(b"isto nao e ofx")


def test_parse_csv_e_ofx_convergem_quando_dados_sao_iguais():
    csv_bytes = (
        "data;descricao;valor\n"
        "25/09/2026;PIX RECEBIDO;650,00\n"
    ).encode("utf-8")
    ofx = """<OFX>
<STMTTRN>
<DTPOSTED>20260925</DTPOSTED>
<TRNAMT>650.00</TRNAMT>
<MEMO>PIX RECEBIDO</MEMO>
</STMTTRN>
</OFX>""".encode("utf-8")
    a = parse_csv(csv_bytes)
    b = parse_ofx(ofx)
    assert len(a) == len(b) == 1
    assert a[0].data == b[0].data
    assert a[0].valor == b[0].valor
