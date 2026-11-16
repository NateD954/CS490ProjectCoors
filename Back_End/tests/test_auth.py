"""Tests for the real login check in app/auth.py.

Every other test replaces this check, so it is tested here on its own. The tests make
their own signing keys and fake the request to Clerk, so no real service is contacted.
"""

import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth

SECRET = "sk_test_secret"
KID = "key-1"
REJECTED = "You do not have permission to access this resource. Please check your credentials."


# ---- helpers -----------------------------------------------------------------


def newKey():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def pemOf(key):
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def jwkFor(key, kid=KID):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = kid
    return jwk


def makeToken(key, sub="user_123", expiresIn=300, kid=KID):
    payload = {"exp": int(time.time()) + expiresIn}
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, pemOf(key), algorithm="RS256", headers={"kid": kid})


class FakeJwksResponse:
    def __init__(self, jwks, error=None):
        self.jwks = jwks
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.jwks


def fakeClerk(monkeypatch, keys=(), getError=None, statusError=None):
    """Replace the request to Clerk for its public keys. Returns the requests made."""
    calls = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, headers=None, **kwargs):
            calls.append({"url": url, "headers": headers})
            if getError:
                raise getError
            return FakeJwksResponse({"keys": list(keys)}, statusError)

    monkeypatch.setattr(auth, "httpx", SimpleNamespace(Client=FakeClient))
    return calls


def check(token):
    return auth.getCurrentUserId(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def assertRejected(token):
    with pytest.raises(HTTPException) as err:
        check(token)
    assert err.value.status_code == 401
    assert err.value.detail == REJECTED
    return err


@pytest.fixture(scope="module")
def signingKey():
    return newKey()


@pytest.fixture(scope="module")
def otherKey():
    return newKey()


@pytest.fixture(autouse=True)
def secretKey(monkeypatch):
    monkeypatch.setattr(auth, "CLERK_SECRET_KEY", SECRET)


# ---- accepted ----------------------------------------------------------------


def test_a_valid_token_gives_the_users_id(monkeypatch, signingKey):
    calls = fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assert check(makeToken(signingKey, sub="user_123")) == "user_123"
    assert calls[0]["url"].endswith("/v1/jwks")
    assert calls[0]["headers"]["Authorization"] == f"Bearer {SECRET}"


def test_the_matching_key_is_picked_when_clerk_lists_several(monkeypatch, signingKey, otherKey):
    fakeClerk(monkeypatch, keys=[jwkFor(otherKey, kid="key-old"), jwkFor(signingKey, kid="key-2")])

    assert check(makeToken(signingKey, sub="user_456", kid="key-2")) == "user_456"


# ---- rejected ----------------------------------------------------------------


def test_an_expired_token_is_rejected(monkeypatch, signingKey):
    fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assertRejected(makeToken(signingKey, expiresIn=-60))


def test_a_token_signed_with_the_wrong_key_is_rejected(monkeypatch, signingKey, otherKey):
    fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assertRejected(makeToken(otherKey))  # claims to be key-1 but was not signed by it


def test_a_token_whose_key_id_clerk_does_not_list_is_rejected(monkeypatch, signingKey):
    fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assertRejected(makeToken(signingKey, kid="unknown-key"))


def test_an_unsigned_token_is_rejected(monkeypatch, signingKey):
    fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])
    payload = {"sub": "user_123", "exp": int(time.time()) + 300}
    unsigned = jwt.encode(payload, None, algorithm="none", headers={"kid": KID})

    assertRejected(unsigned)


def test_a_token_without_a_user_id_is_rejected(monkeypatch, signingKey):
    fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assertRejected(makeToken(signingKey, sub=None))


def test_text_that_is_not_a_token_is_rejected_without_contacting_clerk(monkeypatch, signingKey):
    calls = fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])

    assertRejected("not-a-token")

    assert calls == []


def test_a_failed_request_to_clerk_rejects_the_user(monkeypatch, signingKey):
    fakeClerk(monkeypatch, getError=RuntimeError("Clerk is unreachable"))

    assertRejected(makeToken(signingKey))


def test_an_error_response_from_clerk_rejects_the_user(monkeypatch, signingKey):
    fakeClerk(monkeypatch, statusError=RuntimeError("429 Too Many Requests"))

    assertRejected(makeToken(signingKey))


def test_the_rejection_message_reveals_nothing_about_why(monkeypatch, signingKey):
    fakeClerk(monkeypatch, getError=RuntimeError(f"failed with {SECRET}"))

    err = assertRejected(makeToken(signingKey))

    assert SECRET not in str(err.value.detail)
    assert "RuntimeError" not in str(err.value.detail)


# ---- server setup ------------------------------------------------------------


def test_a_missing_secret_key_is_a_server_error_and_clerk_is_not_contacted(monkeypatch, signingKey):
    calls = fakeClerk(monkeypatch, keys=[jwkFor(signingKey)])
    monkeypatch.setattr(auth, "CLERK_SECRET_KEY", None)

    with pytest.raises(HTTPException) as err:
        check(makeToken(signingKey))

    assert err.value.status_code == 500
    assert calls == []
