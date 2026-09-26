from fastapi import HTTPException
def erro(status_code:int,codigo:str,mensagem:str|None=None):
    return HTTPException(status_code=status_code,detail={"erro":codigo,"mensagem":mensagem or codigo})
