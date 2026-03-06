from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.database import get_session
from app.models import Client, User
from app.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: User
    client: Client


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(credentials.credentials)
    user = session.get(User, payload.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is unavailable")

    client = session.get(Client, user.client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace is unavailable")

    return Principal(user=user, client=client)


def require_role(*allowed_roles: str):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return principal

    return dependency


def require_client_access(client_id: str, principal: Principal) -> Client:
    if principal.client.id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is not allowed")
    return principal.client
