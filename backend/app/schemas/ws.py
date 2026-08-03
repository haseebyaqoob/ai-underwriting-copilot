from pydantic import BaseModel


class WsTokenOut(BaseModel):
    ws_token: str
    expires_in_seconds: int
