"""Fail-closed validation of Google-signed Pub/Sub OIDC identity tokens."""

from __future__ import annotations


class AuthenticationError(ValueError):
    pass


def verify_pubsub_oidc(
    authorization: str | None,
    *,
    audience: str,
    expected_service_account: str,
) -> dict[str, object]:
    if not audience or not expected_service_account:
        raise AuthenticationError("worker identity configuration is incomplete")
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AuthenticationError("empty bearer token")

    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(token, Request(), audience=audience)
    except Exception as exc:
        raise AuthenticationError("invalid signed identity token") from exc
    if claims.get("email") != expected_service_account:
        raise AuthenticationError("unexpected service account")
    if claims.get("email_verified") is not True:
        raise AuthenticationError("service account email is not verified")
    if claims.get("aud") != audience:
        raise AuthenticationError("unexpected audience")
    return claims
