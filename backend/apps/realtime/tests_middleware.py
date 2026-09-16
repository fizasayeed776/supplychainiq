"""
Tests for realtime/middleware.py — JWTAuthMiddleware.

Tests the token-resolution logic directly without requiring a real WebSocket
connection: we call get_user_from_token() and build minimal ASGI scopes to
exercise the middleware's __call__ path.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase

User = get_user_model()


# =============================================================================
# get_user_from_token — unit tests for the DB-backed resolver
# =============================================================================

class GetUserFromTokenTests(TransactionTestCase):
    """Direct tests of the async DB helper; no sockets needed."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mwtest", email="mw@test.com", password="pass"
        )

    def test_valid_token_resolves_to_user(self):
        """A freshly minted access token must resolve to the originating user."""
        from rest_framework_simplejwt.tokens import AccessToken
        token = str(AccessToken.for_user(self.user))

        from apps.realtime.middleware import get_user_from_token
        resolved = asyncio.run(get_user_from_token(token))
        self.assertEqual(resolved.id, self.user.id)

    def test_invalid_token_resolves_to_anonymous(self):
        from apps.realtime.middleware import get_user_from_token
        resolved = asyncio.run(get_user_from_token("not.a.valid.jwt"))
        self.assertIsInstance(resolved, AnonymousUser)

    def test_expired_token_resolves_to_anonymous(self):
        """An expired token (tampered exp) must NOT resolve to a real user."""
        import time
        import jwt as pyjwt
        from django.conf import settings

        # Build a token that expired 1 hour ago
        payload = {
            "user_id": str(self.user.id),
            "exp": int(time.time()) - 3600,
            "iat": int(time.time()) - 7200,
            "token_type": "access",
        }
        secret = settings.SECRET_KEY
        expired_token = pyjwt.encode(payload, secret, algorithm="HS256")

        from apps.realtime.middleware import get_user_from_token
        resolved = asyncio.run(get_user_from_token(expired_token))
        self.assertIsInstance(resolved, AnonymousUser)

    def test_empty_string_token_resolves_to_anonymous(self):
        from apps.realtime.middleware import get_user_from_token
        resolved = asyncio.run(get_user_from_token(""))
        self.assertIsInstance(resolved, AnonymousUser)


# =============================================================================
# JWTAuthMiddleware.__call__ — scope-injection tests
# =============================================================================

class JWTAuthMiddlewareTests(TransactionTestCase):
    """Verify the middleware populates scope['user'] correctly before
    delegating to the inner ASGI app."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mwscope", email="mwscope@test.com", password="pass"
        )

    def _make_scope(self, query_string=b"", headers=None):
        return {
            "type": "websocket",
            "query_string": query_string,
            "headers": headers or [],
        }

    def _run_middleware(self, scope):
        """Run the middleware and return the (possibly modified) scope."""
        from apps.realtime.middleware import JWTAuthMiddleware

        received_scope = {}

        async def inner(s, receive, send):
            received_scope.update(s)

        middleware = JWTAuthMiddleware(inner)
        asyncio.run(middleware(scope, None, None))
        return received_scope

    def test_valid_query_token_sets_real_user(self):
        from rest_framework_simplejwt.tokens import AccessToken
        token = str(AccessToken.for_user(self.user))

        scope = self._make_scope(query_string=f"token={token}".encode())
        result = self._run_middleware(scope)

        self.assertFalse(result["user"].is_anonymous)
        self.assertEqual(result["user"].id, self.user.id)

    def test_missing_token_sets_anonymous_user(self):
        """No token in query string or headers → AnonymousUser.
        Regression: the empty-token race condition (Step 6/7) that caused
        authenticated users to intermittently get 4403 errors must not
        occur when there is genuinely no token."""
        scope = self._make_scope(query_string=b"")
        result = self._run_middleware(scope)

        self.assertIsInstance(result["user"], AnonymousUser)

    def test_invalid_token_sets_anonymous_user(self):
        scope = self._make_scope(query_string=b"token=garbage.token.here")
        result = self._run_middleware(scope)

        self.assertIsInstance(result["user"], AnonymousUser)

    def test_header_token_is_read_when_query_string_empty(self):
        """Token in Sec-WebSocket-Protocol header must be used if no query
        string token is present."""
        from rest_framework_simplejwt.tokens import AccessToken
        token = str(AccessToken.for_user(self.user))

        scope = self._make_scope(
            query_string=b"",
            headers=[(b"sec-websocket-protocol", token.encode())],
        )
        result = self._run_middleware(scope)

        self.assertFalse(result["user"].is_anonymous)
        self.assertEqual(result["user"].id, self.user.id)

    def test_query_string_token_takes_precedence_over_header(self):
        """When both query-string and header tokens are present, the
        query-string token wins."""
        from rest_framework_simplejwt.tokens import AccessToken
        real_token = str(AccessToken.for_user(self.user))

        scope = self._make_scope(
            query_string=f"token={real_token}".encode(),
            headers=[(b"sec-websocket-protocol", b"garbage.header.token")],
        )
        result = self._run_middleware(scope)

        self.assertFalse(result["user"].is_anonymous)
        self.assertEqual(result["user"].id, self.user.id)
