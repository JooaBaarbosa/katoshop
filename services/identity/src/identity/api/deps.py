from fastapi import Request

from identity.application.auth_service import AuthService


def auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service
