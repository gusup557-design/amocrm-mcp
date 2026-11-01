# ChatGPT Native Multi-Account OAuth for amoCRM MCP

**Status:** Approved architecture; implementation not started  
**Date:** 2026-11-01  
**Target branch:** `feat/chat-voice-language-foundation`  
**Scope:** Replace operator-password authorization and MCP-session account selection with one OAuth grant per ChatGPT-connected amoCRM account.

## 1. Product outcome

A user adds the remote amoCRM MCP server in ChatGPT, completes the server's OAuth flow, and authorizes one amoCRM account. ChatGPT owns the connected-account list, the “connect another account” action, and disconnect controls. A second amoCRM account is connected by completing the same OAuth flow again. The server does not expose an account catalogue or an account-switching tool.

Each authenticated MCP request is scoped to the amoCRM account bound to the exact bearer token presented by ChatGPT. The model cannot supply or override an account ID.

## 2. Repository facts verified before design

- `server.py` imports `provider`, `register_amo_routes`, and `amo_access_token` from `oauth_backend.py`; this is the active authorization implementation.
- `oauth_backend.py` currently sends MCP authorization to `/oauth/consent`, which requires `MCP_ADMIN_PASSWORD`.
- The upstream amoCRM integration-button flow currently uses `/connect`, `/oauth/secrets`, and `/oauth/callback`.
- The callback stores encrypted CRM credentials in `amocrm_connections`, whose primary key is `account_id`.
- MCP tokens are stored in `mcp_oauth_tokens`; the current JSON payload contains client/scopes/resource but no CRM grant/account binding.
- `amo_access_token()` resolves an account through `mcp_account_selections` using an MCP principal and Streamable HTTP session ID.
- `server.py` exposes `list_amocrm_connections`, `select_amocrm_account`, `get_selected_amocrm_account`, and `disconnect_amocrm_connection`.
- `mcp_account_selections` is an existing Supabase table. This feature stops using it; it does not drop it.
- `requirements.txt` currently declares `mcp[cli]>=1.30,<2`.
- Supabase project schema inspection showed `amocrm_connections`, `amocrm_oauth_pending`, `mcp_oauth_clients`, `mcp_oauth_authorization_codes`, `mcp_oauth_tokens`, `mcp_oauth_pending`, `mcp_oauth_codes`, and `mcp_account_selections`. The DB migration history includes six migrations through `20261101051219_multi_account_registry_and_session_selection`; the SQL file in this repository is named `20261101060000_multi_account_registry_and_session_selection.sql`. Reconcile this version mismatch before applying any migration.
- The live `amocrm_connections` and `mcp_oauth_tokens` tables currently report zero rows; `amocrm_oauth_pending`, MCP pending/code tables have records. Do not assume stale pending records are safe to delete without expiry-aware cleanup.

## 3. Chosen architecture

Two OAuth layers remain distinct:

1. **ChatGPT → MCP authorization server:** OAuth Authorization Code + PKCE S256. The MCP server issues its own short-lived access token and rotating refresh token.
2. **MCP authorization server → amoCRM:** the existing official amoCRM integration-button OAuth process. Its callback must be bound to the exact pending MCP authorization transaction.

The amoCRM access/refresh token is encrypted at rest and never returned to ChatGPT. The MCP bearer token is a separate opaque credential issued by this server and is bound to a server-side grant.

### 3.1 Request flow

1. ChatGPT discovers the MCP protected-resource metadata and the authorization-server metadata.
2. ChatGPT starts the OAuth authorization-code flow with PKCE S256 and the exact MCP resource indicator.
3. The active provider creates a short-lived `mcp_oauth_pending` transaction containing client ID, redirect URI, original ChatGPT state, PKCE challenge, requested scopes, and resource.
4. The provider redirects the browser to a transaction-specific amoCRM linking page. This page contains the official amoCRM integration button; it has no owner password, no account catalogue, and no manual account selector.
5. The page creates a fresh random upstream state and stores a one-to-one binding between that state and the pending MCP transaction.
6. The amoCRM `/oauth/secrets` webhook stores the integration client ID and encrypted client secret against that exact upstream state.
7. The amoCRM callback validates and consumes the same state, exchanges the upstream code, fetches `/api/v4/account`, validates the CRM domain, and upserts the encrypted connection by `account_id`.
8. The callback creates the MCP authorization code for the original ChatGPT redirect URI. It carries the CRM account identity as server-validated authorization context; it never accepts an account ID from a model tool argument.
9. ChatGPT exchanges the MCP code and PKCE verifier at the MCP token endpoint. The server creates one grant and an access/refresh token pair bound to that grant.
10. Every MCP tool request resolves the account from the validated access token's grant. The MCP session ID is not an identity or account selector.
11. ChatGPT can repeat the flow to connect another amoCRM account. Each authorization code exchange creates a separate grant.

### 3.2 Account and grant data model

Keep `amocrm_connections` as the upstream credential store, keyed by amoCRM `account_id`. Multiple MCP grants may reference the same CRM connection.

Add a server-only `mcp_oauth_grants` table:

- `grant_id uuid primary key`
- `client_id text not null references mcp_oauth_clients(client_id)`
- `account_id bigint not null references amocrm_connections(account_id)`
- `scopes text[] not null`
- `created_at timestamptz not null default now()`
- `revoked_at timestamptz null`

Add `grant_id uuid` to `mcp_oauth_tokens`, with a foreign key to `mcp_oauth_grants` and an index. Both access and refresh token rows carry the same grant ID. The token hash remains the only stored representation of the raw MCP token. The JSON payload retains the exact resource and expiry data needed by the provider.

Authorization-code exchange must atomically consume the one-time code, create the grant, and insert the access/refresh token hashes. Prefer a narrowly scoped Postgres RPC with a fixed `search_path`, `SECURITY DEFINER`, and execution granted only to `service_role`; do not split a single-use consume operation into a read followed by an unguarded delete.

Refresh-token rotation must atomically revoke the presented refresh token and create the replacement pair while preserving the grant ID, account binding, scopes, and resource. A revoked grant invalidates every access and refresh token belonging to it.

### 3.3 Runtime identity

Use `get_access_token()` from the MCP Python SDK inside authenticated tool handlers. The access token's server-issued claims identify the grant; the provider must validate that the grant exists, is not revoked, and belongs to the same registered OAuth client before a CRM request proceeds.

The account resolver must:
- read the authenticated request token from MCP auth context;
- load the active grant by its grant ID;
- load exactly the grant's `amocrm_connections.account_id`;
- fail closed if token, grant, connection, or resource binding is missing or invalid;
- never fall back to “the only connected account”, session state, a global account, or model-supplied arguments.

A `get_profile` tool returns only the profile represented by the current token. Mark it with `_meta[\"openai/profile\"] = true`. Its `id` is a stable opaque identifier derived server-side from the immutable amoCRM `account_id` (for example, HMAC-SHA256 with a dedicated stable profile key); display metadata includes the current account name and CRM domain. It accepts no account selector and returns no tokens or secrets.

## 4. OAuth and metadata compatibility

- Preserve the MCP SDK's Authorization Code + PKCE provider and DCR route initially; do not add another OAuth framework.
- Require PKCE S256, exact registered redirect URI validation, one-time authorization codes, short authorization-code expiry, exact MCP resource echo, and client binding at token exchange.
- The authorization server must publish metadata at `/.well-known/oauth-authorization-server`; the MCP resource must publish Protected Resource Metadata at the SDK-supported well-known path. Both must identify the same canonical issuer/resource values used by `AuthSettings`.
- The ChatGPT integration must advertise only token-endpoint authentication methods the deployed provider actually accepts. Confirm DCR behavior and the supported public-client method against the current OpenAI guide and the pinned MCP SDK before rollout.
- Do not advertise `authorization_response_iss_parameter_supported: true` unless every authorization response, including errors, contains the exact issuer parameter. The current MCP SDK authorization handler's error redirect does not visibly add RFC 9207 `iss`; therefore the first implementation must either add a tested complete RFC 9207 override or leave the flag false and use ChatGPT's callback-ID-specific redirect. Do not claim stable callback support without this verification.
- Keep the `resource` value canonical and identical in authorization request, pending record, authorization code, issued access/refresh token, and resource-server validation.

## 5. Upstream callback transaction integrity and cross-user linking risk

The amoCRM button's state is a separate, random, single-use upstream state. It is cryptographically random and stored only as a binding to the exact pending MCP transaction, which already contains the ChatGPT client ID, redirect URI, original state, PKCE challenge, scopes, and resource. A callback cannot be reassigned to another pending transaction. This prevents callback swapping and cross-transaction confusion.

The MCP server does not receive a stable ChatGPT human-user identifier in the OAuth authorization request. Therefore, do not claim that server-side state alone proves the human identity of the ChatGPT user. PKCE and the exact registered redirect URI protect authorization-code redemption; ChatGPT itself owns the host account/session binding. The implementation must never accept an account ID from a model tool argument, browser-supplied profile, or a different pending transaction. Treat any attempt to reuse an upstream state across MCP transactions as a security failure. Store its hash or exact opaque value only with the corresponding MCP transaction ID, expiry, and webhook status. The secrets webhook and callback must both resolve the same pending row. The callback must consume it once and must not select an MCP transaction from browser session, referer, query-supplied account ID, or most-recent-pending heuristics.

Validate:
- pending transaction exists and is unexpired;
- upstream state matches and has not been consumed;
- integration credentials were stored for this same state;
- callback domain is an allowed amoCRM/Kommo hostname;
- upstream account identity is obtained from the authenticated amoCRM API response;
- the pending MCP transaction is still valid and its client/redirect/resource values remain unchanged.

The callback should return a safe completion page only after token exchange and MCP authorization-code creation. It must not print secrets, authorization codes, raw state, or tokens.

## 6. Revocation and shared CRM connections

Revoking one MCP grant revokes only that grant and its MCP token family. It must not delete or rotate the shared amoCRM credential row while another active grant references the same account. When the final active grant is revoked, local CRM credential retention is a product decision; recommended default is to delete the encrypted local CRM credentials after the last grant, while not claiming that the upstream amoCRM integration itself was remotely revoked unless amoCRM's supported revocation API is verified.

The existing explicit account-disconnect tool is incompatible with host-managed per-connection lifecycle because it accepts an arbitrary account ID. Remove it from the exposed tool set or replace it with no account argument and current-grant semantics. Do not permit a caller to disconnect a different account by supplying an ID.

## 7. Legacy and non-goals

- Remove the operator password requirement and `MCP_ADMIN_PASSWORD` / `MCP_AUTH_PASSWORD` environment documentation once the new flow is active.
- Remove the password form and password comparison from the active OAuth path.
- Stop exposing the account catalogue and manual session-selection tools.
- Stop importing or calling `get_mcp_selection_identity`, `get_selected_amocrm_account_id`, and `set_selected_amocrm_account` from runtime CRM resolution.
- Keep `mcp_account_selections` intact during this change; it becomes unused legacy data and can be dropped in a separate reviewed cleanup.
- Do not change global AMOCHAT/ElevenLabs provider configuration in this feature. Those credentials are process-global today; preserve the existing fail-closed multiple-account guard and clearly test that it remains in place.
- Do not change production deployment, production environment variables, or merge the existing PR as part of this specification.

## 8. Security invariants

1. No MCP request can select or change its CRM account through tool arguments.
2. One access token resolves to one active grant and one CRM account.
3. No token from one grant can read or mutate another grant's account.
4. ChatGPT MCP tokens and amoCRM tokens are distinct; CRM tokens are encrypted and server-only.
5. PKCE S256, resource binding, client binding, redirect URI validation, token expiry, and single-use authorization codes are enforced.
6. amoCRM secrets webhook and callback are bound to one upstream state and one pending MCP transaction.
7. Refresh rotation and grant revocation are race-safe and scoped to one grant.
8. Revoking one grant does not invalidate another grant that references the same CRM account.
9. Profile data is derived from the validated token and contains no secret.
10. Any missing/ambiguous identity fails closed.

## 9. Acceptance tests

- Connect CRM A; issue token A; every CRM tool request resolves only account A.
- Connect CRM B using the same ChatGPT MCP server; issue token B; token B resolves only B while token A still resolves A.
- Connect two separate grants to the same CRM account; revoking one leaves the other grant operational.
- Attempt to supply account ID B while authenticated as A; tool schema exposes no account selector and resolver remains A.
- Missing, expired, revoked, wrong-client, wrong-resource, and unknown-grant tokens are rejected before CRM access.
- Wrong/missing/replayed/expired upstream state cannot store secrets, exchange amoCRM code, or issue an MCP code.
- A secrets webhook for transaction A cannot modify transaction B.
- A callback for transaction A cannot complete pending MCP transaction B.
- Authorization code replay and refresh-token replay fail; concurrent refreshes cannot create divergent token families.
- The profile tool returns one stable opaque profile ID for the same account across reconnects and different display metadata when the account differs.
- Existing global provider scope guard still rejects global AMOCHAT/ElevenLabs use when multiple CRM connections are present.
- No tool result, logs, metadata, or profile response contains raw OAuth credentials or token values.

## 10. External references

- OpenAI Authentication guide: https://developers.openai.com/plugins/build/auth
- OpenAI MCP server guide: https://developers.openai.com/plugins/build/mcp-server
- MCP Python SDK authorization docs: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/authorization.md
- OAuth 2.0 Security BCP (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- OAuth Authorization Server Issuer Identification (RFC 9207): https://www.rfc-editor.org/rfc/rfc9207
- OAuth Resource Indicators (RFC 8707): https://www.rfc-editor.org/rfc/rfc8707
- Consensus security research report: `docs/research/2026-11-01-multi-account-oauth-security-research.md`

## 11. Decisions still requiring product confirmation before implementation

1. **Last-grant disconnect:** recommended delete of local encrypted amoCRM credentials when the last active MCP grant is revoked. If reconnect convenience or other server features require retention, retain credentials but keep them inaccessible to revoked grants.
2. **Global chat/voice integrations:** remain blocked for multiple CRM accounts under the existing global-secret guard; account-scoping them is a separate feature.
3. **OAuth issuer callback mode:** use callback-ID-specific redirect until complete RFC 9207 success/error issuer support is verified in the deployed SDK/provider. Stable callback is a later compatibility improvement, not an assumption.
