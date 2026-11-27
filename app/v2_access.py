"""Authenticate platform gateways and independent reviewers for the action API."""

from __future__ import annotations

import hmac
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from time import monotonic

import yaml
from fastapi import HTTPException, Request
from pydantic import Field, model_validator

from pehchaan_live.contracts import Contract, Identifier
from pehchaan_live.policy import Policy, load_policy, reference_policy
from pehchaan_live.rollout import selected_policy
from pehchaan_live.settings import live_settings


class TenantConfig(Contract):
    id: Identifier
    token_env: Identifier
    review_token_env: Identifier | None = None
    policy: str | None = Field(default=None, min_length=1, max_length=512)
    rollout: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def one_policy_source(self):
        if bool(self.policy) == bool(self.rollout):
            raise ValueError("configure one policy file or tenant rollout pointer")
        return self


@dataclass(frozen=True)
class Credential:
    tenant: str
    policy: Policy | Path
    can_review: bool
    token: str = field(repr=False)

    def policy_for(self, call_id: str) -> Policy:
        if isinstance(self.policy, Policy):
            return self.policy
        return selected_policy(self.policy, self.tenant, call_id)


@lru_cache(maxsize=4)
def _configured(path: str) -> tuple[tuple[TenantConfig, Policy | Path], ...]:
    filename = Path(path).resolve()
    rows = [TenantConfig.model_validate(row) for row in yaml.safe_load(filename.read_text(encoding="utf-8"))]
    if not 0 < len(rows) <= 32 or len({row.id for row in rows}) != len(rows):
        raise ValueError("configure between 1 and 32 distinct tenant IDs")
    return tuple(
        (row, load_policy(filename.parent / row.policy) if row.policy else (filename.parent / row.rollout).resolve())
        for row in rows
    )


def _credentials() -> list[Credential]:
    if config := os.getenv("PEHCHAAN_V2_TENANTS"):
        tenants = _configured(config)
    elif os.getenv("ENV") != "production" and os.getenv("PEHCHAAN_V2_TOKEN"):
        tenant = TenantConfig(id="local", token_env="PEHCHAAN_V2_TOKEN", review_token_env="PEHCHAAN_V2_REVIEW_TOKEN",
                              policy=os.getenv("PEHCHAAN_V2_POLICY", "delivery"))
        tenants = ((tenant, reference_policy(tenant.policy)),)
    else:
        return []
    credentials = []
    for tenant, policy in tenants:
        for name, can_review in ((tenant.token_env, False), (tenant.review_token_env, True)):
            if name and (token := os.getenv(name)):
                if len(token) < 24 or len(token) > 256 or not token.isascii() or not token.isprintable() or " " in token:
                    raise ValueError("gateway tokens must be 24–256 printable ASCII characters without spaces")
                credentials.append(Credential(tenant.id, policy, can_review, token))
    if len({item.token for item in credentials}) != len(credentials):
        raise ValueError("gateway and reviewer tokens must be distinct across all tenants")
    return credentials


_window: dict[str, deque] = defaultdict(deque)


def authenticate(request: Request) -> Credential:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.isascii() or not 24 <= len(token) <= 256:
        raise HTTPException(401, "platform_credential_required")
    try:
        credentials = _credentials()
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise HTTPException(503, "invalid_platform_configuration") from exc
    credential = next((entry for entry in credentials if hmac.compare_digest(token, entry.token)), None)
    if credential is None:
        raise HTTPException(401, "platform_credential_required")
    now = monotonic()
    window = _window[credential.tenant]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= live_settings()["runtime"]["requests_per_minute"]:
        raise HTTPException(429, "tenant_request_quota")
    window.append(now)
    return credential
