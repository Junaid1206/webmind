from hmac import compare_digest

from fastapi import HTTPException, Request, status

from backend.app.core.config import settings


def require_api_key(request: Request) -> None:
    """
    Protect API endpoints with the application's API key.

    Authentication is enforced only when settings.webmind_api_key is configured.
    This keeps local development convenient while still allowing production
    deployments to require authentication.

    Accepted headers:

        X-API-Key: <APP_API_KEY>

    or:

        Authorization: Bearer <APP_API_KEY>
    """

    configured_api_key = settings.webmind_api_key

    # No application API key configured:
    # allow unauthenticated access for local MVP/development.
    if not configured_api_key:
        return

    # Option 1: X-API-Key
    provided_api_key = request.headers.get("X-API-Key")

    # Option 2: Authorization: Bearer <key>
    if not provided_api_key:
        authorization = request.headers.get("Authorization", "")

        if authorization.lower().startswith("bearer "):
            provided_api_key = authorization[7:].strip()

    # Missing key
    if not provided_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Invalid key
    if not compare_digest(provided_api_key, configured_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )