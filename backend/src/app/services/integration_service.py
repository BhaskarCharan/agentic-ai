"""Manages OAuth connections to external toolkits (Gmail, LinkedIn) via
Composio - the Service layer for account linking (Phase 1 of
`MULTI_AGENT_ROADMAP.md`).

This is the one file that imports the `composio` SDK directly - same
"one file owns the third-party client" convention as `agent/llm.py` for
Gemini or `db.py` for Motor. The Composio Python SDK is synchronous
throughout (confirmed live against a real Composio account while building
this: `connected_accounts.link`, `auth_configs.list`/`create` are all
blocking HTTP calls, not async) - every call here goes through
`asyncio.to_thread` so it doesn't block the event loop other requests are
running on.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from composio import Composio

from app.config import settings

# Toolkits this app knows how to link. The Gmail/LinkedIn specialist agents
# (Phase 2/3) will only work once their entry here has an ACTIVE connected
# account - adding a toolkit here is necessary but not sufficient for that.
SUPPORTED_TOOLKITS = ["gmail", "linkedin"]

# Per-toolkit "who am I" action + how to pull a human-readable label out of
# its response - a connection's status/token metadata alone never includes
# the account's email or name, so showing one means actually calling the
# connected service, not just checking that a connection exists.
_IDENTITY_TOOLS: dict[str, tuple[str, Callable[[dict[str, Any]], str | None]]] = {
    "gmail": ("GMAIL_GET_PROFILE", lambda data: data.get("emailAddress")),
    "linkedin": (
        "LINKEDIN_GET_MY_INFO",
        lambda data: (
            f"{data.get('localizedFirstName', '')} {data.get('localizedLastName', '')}".strip()
            or None
        ),
    ),
}


@lru_cache
def get_composio_client() -> Composio:
    """Lazily constructed, cached for the process lifetime - same pattern as
    `config.get_settings()`. Deferred rather than built at import time
    because `Composio(api_key=...)` raises immediately if no key is
    configured (confirmed live), and the test suite never configures one -
    it never hits an integrations route, so it must never be forced to
    construct this client just by importing this module.
    """
    return Composio(api_key=settings.composio_api_key)


@dataclass
class IntegrationStatus:
    toolkit: str
    connected: bool
    # Raw ISO8601 string from Composio, not parsed - Composio's own SDK
    # treats these as opaque sortable strings internally too (see
    # `_get_or_create_auth_config` below), so there's no need to parse them
    # into `datetime` just to pass through to the API response.
    connected_since: str | None = None
    # Human-readable identity (email for Gmail, name for LinkedIn) - best
    # effort, from `_fetch_label` below. None if the toolkit has no identity
    # tool configured or the live lookup fails for any reason.
    label: str | None = None


class IntegrationService:
    def __init__(self, client: Composio, user_id: str) -> None:
        self._client = client
        self._user_id = user_id

    async def list_statuses(self) -> list[IntegrationStatus]:
        return list(
            await asyncio.gather(*(self._status_for(toolkit) for toolkit in SUPPORTED_TOOLKITS))
        )

    async def _status_for(self, toolkit: str) -> IntegrationStatus:
        accounts = await asyncio.to_thread(
            self._client.connected_accounts.list,
            user_ids=[self._user_id],
            toolkit_slugs=[toolkit],
            statuses=["ACTIVE"],
        )
        if not accounts.items:
            return IntegrationStatus(toolkit=toolkit, connected=False)

        label = await asyncio.to_thread(self._fetch_label, toolkit)
        return IntegrationStatus(
            toolkit=toolkit,
            connected=True,
            connected_since=accounts.items[0].created_at,
            label=label,
        )

    def _fetch_label(self, toolkit: str) -> str | None:
        """Best-effort: call the connected service's own "who am I" action
        to get a human-readable identity for the sidebar. Deliberately never
        raises - a hiccup fetching a display label (rate limit, a toolkit
        with no identity tool configured, a transient API error) must never
        break the connection *status* check above, which is the part that
        actually matters.

        Tool execution requires pinning a specific toolkit version -
        `dangerously_skip_version_check=True` is the obvious shortcut, but
        Composio's own error message warns it "might cause unexpected
        behavior when new versions of the tools are released"; pulling the
        toolkit's current version via `toolkits.get(toolkit).meta.version`
        first avoids that, verified live before writing this.
        """
        identity = _IDENTITY_TOOLS.get(toolkit)
        if identity is None:
            return None
        tool_slug, extract_label = identity

        try:
            version = self._client.toolkits.get(toolkit).meta.version
            result = self._client.tools.execute(
                tool_slug, arguments={}, user_id=self._user_id, version=version
            )
        except Exception:
            return None

        if not result.get("successful"):
            return None
        return extract_label(result.get("data") or {})

    async def initiate_connection(self, toolkit: str) -> str:
        """Kick off the OAuth consent flow for a toolkit, returning the URL
        the frontend should send the user to. Auto-provisions a
        Composio-managed auth config for the toolkit on first use - no
        manual dashboard setup required.
        """
        if toolkit not in SUPPORTED_TOOLKITS:
            raise ValueError(f"Unsupported toolkit: {toolkit!r}")

        auth_config_id = await asyncio.to_thread(self._get_or_create_auth_config, toolkit)
        connection_request = await asyncio.to_thread(
            self._client.connected_accounts.link, self._user_id, auth_config_id
        )
        return connection_request.redirect_url

    async def disconnect(self, toolkit: str) -> None:
        """Revoke and remove every ACTIVE connected account for a toolkit.

        Idempotent - a toolkit with nothing connected is a no-op rather than
        an error, matching the usual semantics of DELETE.
        """
        if toolkit not in SUPPORTED_TOOLKITS:
            raise ValueError(f"Unsupported toolkit: {toolkit!r}")

        await asyncio.to_thread(self._disconnect, toolkit)

    def _disconnect(self, toolkit: str) -> None:
        accounts = self._client.connected_accounts.list(
            user_ids=[self._user_id], toolkit_slugs=[toolkit], statuses=["ACTIVE"]
        )
        for account in accounts.items:
            # `revoke_on_delete=True` actually invalidates the token with
            # the provider (Google/LinkedIn), not just Composio's own
            # bookkeeping - clicking "Disconnect" should mean this app can
            # no longer act on the user's behalf at all, not just that
            # Composio stops listing the connection.
            self._client.connected_accounts.delete(nanoid=account.id, revoke_on_delete=True)

    def _get_or_create_auth_config(self, toolkit: str) -> str:
        """Find the newest Composio-managed auth config for this toolkit,
        creating one on first use.

        Mirrors what Composio's own `toolkits.authorize()` convenience
        method does internally (read via `inspect.getsource` while building
        this) - but that method calls the *deprecated*
        `connected_accounts.initiate()`, which Composio's own docs say is
        being retired for Composio-managed OAuth. This replicates the same
        auto-provisioning logic on top of the non-deprecated
        `connected_accounts.link()` instead. Verified live end-to-end
        (auth config creation + a real redirect URL) against a real
        Composio account while building this.
        """
        existing = self._client.auth_configs.list(toolkit_slug=toolkit)
        if existing.items:
            newest = max(existing.items, key=lambda item: item.created_at)
            return newest.id

        created = self._client.auth_configs.create(
            toolkit=toolkit,
            options={
                "type": "use_composio_managed_auth",
                "tool_access_config": {"tools_for_connected_account_creation": []},
            },
        )
        return created.id
