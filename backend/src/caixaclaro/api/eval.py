import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings

router = APIRouter()


@router.get("/ultima-execucao")
def ultima_execucao():
    caminho = Path(settings().eval_ultima_execucao_path)

    if not caminho.is_file():
        raise HTTPException(
            status_code=404,
            detail="EVAL_ULTIMA_EXECUCAO_NAO_DISPONIVEL",
        )

    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="EVAL_ULTIMA_EXECUCAO_INVALIDA",
        ) from exc
