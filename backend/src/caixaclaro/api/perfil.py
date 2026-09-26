from typing import Literal
from fastapi import APIRouter,Depends
from pydantic import BaseModel,ConfigDict,Field
from ..api.deps import usuario
from ..db import conexao
router=APIRouter()
class PerfilAtualizarIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    nome:str|None=Field(None,max_length=100)
    regime:Literal["MEI","SIMPLES","PF"]|None=None
    mes_abertura_mei:int|None=Field(None,ge=1,le=12)
    ano_abertura_mei:int|None=Field(None,ge=2000,le=2100)
@router.get("")
async def get_perfil(u:dict=Depends(usuario)):
    return {"id":str(u["id"]),"email":u["email"],"nome":u["nome"],"regime":u["regime"],"mes_abertura_mei":u["mes_abertura_mei"],"ano_abertura_mei":u["ano_abertura_mei"],"telegram_chat_id":u["telegram_chat_id"],"criado_em":u["criado_em"].isoformat(),"atualizado_em":u["atualizado_em"].isoformat()}
@router.patch("")
async def patch_perfil(dados:PerfilAtualizarIn,u:dict=Depends(usuario)):
    campos=dados.model_dump(exclude_unset=True)
    if not campos: return {"ok":True,"atualizados":[]}
    sets=[]; valores=[]
    for i,(k,v) in enumerate(campos.items(),1): sets.append(k+" = $"+str(i)); valores.append(v)
    valores.append(u["id"])
    sql="UPDATE users SET "+", ".join(sets)+", atualizado_em=now() WHERE id=$"+str(len(valores))
    async with conexao() as conn: await conn.execute(sql,*valores)
    return {"ok":True,"atualizados":list(campos.keys())}
