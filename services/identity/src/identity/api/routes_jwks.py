from typing import Any

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/.well-known/jwks.json")
async def jwks(request: Request, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"keys": [request.app.state.signing_key.public_jwk()]}
