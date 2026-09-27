"""Guardrail CPF — CONTRATOS_INTERNOS §5 + M4_CONTRATO §6.

Aplicado DEPOIS da classificação. Nunca antes.

Cinco regras:
  6.1 emprestimo   — empréstimo/financiamento nunca vira receita
  6.2 estorno      — estorno/devolução/reembolso nunca vira receita
  6.3 ponte_pf_pj  — retirada de empresa textual reclassifica
  6.4 cpf_proprio  — cpf contraparte == cpf titular => transferência própria
  6.5 tributo      — tributo textual nunca vira gasto comum

Saída: GuardrailResultado (aplicado, categoria_original, categoria_corrigida,
motivo, regra_acionada). NÃO define needs_review — decisão da triagem.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .taxonomia import CategoriaId
from .classificacao import ClassificacaoResultado


RegraAcionada = Literal[
    "cpf_proprio",
    "emprestimo",
    "estorno",
    "ponte_pf_pj",
    "tributo",
]


@dataclass(frozen=True)
class GuardrailResultado:
    aplicado: bool
    categoria_original: CategoriaId
    categoria_corrigida: CategoriaId
    motivo: str
    regra_acionada: RegraAcionada | None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _contem(norm: str, *termos: str) -> bool:
    return any(t in norm for t in termos)


_RECEITAS = ("receita_servico", "receita_venda")


def aplicar_guardrail(
    resultado: ClassificacaoResultado,
    *,
    descricao: str,
    cpf_titular_hash: str | None = None,
    cpf_contraparte_hash: str | None = None,
) -> GuardrailResultado:
    """Aplica as 5 regras na ordem §6.1–6.5. Primeira que casa vence."""
    norm = _norm(descricao)
    cat = resultado.categoria

    # 6.1 emprestimo
    if cat in _RECEITAS and _contem(norm, "emprestimo", "financiamento",
                                    "credito pessoal", "mutuo", "consignado"):
        return GuardrailResultado(
            aplicado=True,
            categoria_original=cat,
            categoria_corrigida="emprestimo",
            motivo="Padrão de empréstimo detectado; recurso temporário "
                   "não é receita tributável.",
            regra_acionada="emprestimo",
        )

    # 6.2 estorno
    if cat in _RECEITAS and _contem(norm, "estorno", "devolucao",
                                    "reembolso", "ressarcimento"):
        return GuardrailResultado(
            aplicado=True,
            categoria_original=cat,
            categoria_corrigida="reembolso",
            motivo="Estorno/devolução detectado; não compõe faturamento.",
            regra_acionada="estorno",
        )

    # 6.3 ponte_pf_pj (apenas textual, D-M4-1 = B)
    # Dispara tanto na reclassificação (classificador errou) quanto na
    # confirmação (classificador acertou) — §7.4 trata ponte como crítico
    # em qualquer caso.
    if cat in ("transferencia_propria", "pessoal_prolabore") and _contem(
        norm, "retirada titular", "distribuicao lucros", "pro labore",
        "pro-labore",
    ):
        return GuardrailResultado(
            aplicado=True,
            categoria_original=cat,
            categoria_corrigida="pessoal_prolabore",
            motivo="Retirada da empresa para o titular; exige confirmação "
                   "explícita (ponte PF↔PJ).",
            regra_acionada="ponte_pf_pj",
        )

    # 6.4 cpf_proprio
    if (
        cat in _RECEITAS
        and cpf_titular_hash
        and cpf_contraparte_hash
        and cpf_titular_hash == cpf_contraparte_hash
    ):
        return GuardrailResultado(
            aplicado=True,
            categoria_original=cat,
            categoria_corrigida="transferencia_propria",
            motivo="CPF da contraparte coincide com o titular; "
                   "movimentação entre contas próprias.",
            regra_acionada="cpf_proprio",
        )

    # 6.5 tributo
    if cat != "imposto_das" and _contem(norm, "das simples", "pgmei", "darf",
                                        "carne leao", "gps inss",
                                        "arrecadacao receita federal"):
        return GuardrailResultado(
            aplicado=True,
            categoria_original=cat,
            categoria_corrigida="imposto_das",
            motivo="Tributo textual inequívoco; prevalece sobre "
                   "classificação preliminar.",
            regra_acionada="tributo",
        )

    return GuardrailResultado(
        aplicado=False,
        categoria_original=cat,
        categoria_corrigida=cat,
        motivo="",
        regra_acionada=None,
    )
