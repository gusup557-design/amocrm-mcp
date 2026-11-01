# ChatGPT Native Multi-Account OAuth Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace password-gated MCP authorization and MCP-session account selection with native ChatGPT-managed OAuth connections, each bound to one amoCRM account.

**Architecture:** Keep the existing MCP Python SDK OAuth provider and amoCRM integration-button flow. Bind the amoCRM callback to the pending ChatGPT OAuth transaction, create a server-side grant per authorization-code exchange, and resolve every CRM request from the validated bearer token's grant. ChatGPT owns connected-account listing and disconnect UI.

**Tech Stack:** Python 3.12, `mcp[cli]>=1.30,<2`, FastMCP, Starlette, Supabase Postgres/PostgREST, amoCRM OAuth, GitHub Actions.

## Global Constraints

- Do not merge PR #1 without separate explicit permission.
- Do not deploy to Production or change Production environment variables without separate explicit permission.
- Do not install or connect additional integrations without separate explicit permission.
- Preserve the existing encrypted amoCRM token storage and refresh-lock behavior.
- Do not expose CRM tokens, MCP bearer tokens, client secrets, or raw OAuth state.
- Do not introduce an account-picker UI, account-selector MCP tool, or session-scoped account routing.
- Keep `mcp_account_selections` in the database during this feature; do not drop it.
- Preserve the fail-closed guard for process-global AMOCHAT/ElevenLabs credentials.
- Verify actual deployed Supabase schema and migration history before applying DDL; the repository migration filename/version differs from the live migration history.
- Use the existing SDK provider; verify exact APIs against the v1.x package before implementation.
- Follow TDD and run `python -m unittest discover -s tests -v` after each affected task.

---

## Task 1: Bind amoCRM linking to one MCP authorization transaction

**Files:**
- Modify: `oauth_backend.py`
- Modify: `tests/test_oauth_redirect.py` only if redirect parameter behavior changes
- Create: `tests/test_oauth_account_linking.py`
- Modify: `supabase/migrations/20261101060000_multi_account_registry_and_session_selection.sql` only if this migration is still unapplied and the change can be safely folded in; otherwise create a new timestamped migration after checking live migration history.

**Interfaces:**
- Existing: `SupabaseOAuthProvider.authorize(client, params) -> str`
- Existing: `register_amo_routes(mcp)`
- Produce: transaction-bound helper functions for creating, loading, and consuming amoCRM OAuth pending state.
- Preserve: `db(method, table, params=None, payload=None, prefer=None)`.

- [ ] **Step 1: Add focused failing tests**

Add tests proving:
- `authorize()` persists client ID, redirect URI, original ChatGPT state, PKCE challenge, scopes, and canonical resource in one pending MCP transaction.
- The linking page creates an independent random upstream amoCRM state and stores a link to exactly one MCP transaction.
- The amoCRM secrets webhook only writes client credentials to the pending row matching that state.
- The callback rejects unknown, expired, consumed, or credential-less state.
- A callback for transaction A cannot finish transaction B.
- A replayed callback cannot create a second MCP authorization code.
- The callback obtains `account_id` from the authenticated amoCRM `/api/v4/account` response, never from request parameters.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_oauth_account_linking -v`

Expected: tests fail because the current /connect flow is independent of the MCP transaction and the callback only deletes an amoCRM pending row after storing the CRM connection.

- [ ] **Step 3: Implement the minimum behavior**

- Replace the active `/oauth/consent` password form with a transaction-specific linking route, e.g. `/oauth/link?transaction=<opaque-id>`.
- Remove the `MCP_ADMIN_PASSWORD` comparison from the active path.
- Persist a separate high-entropy upstream state linked to the MCP pending transaction and its expiry.
- Make `/oauth/secrets` and `/oauth/callback` load the same upstream pending row; validate state, expiry, stored client ID/secret, allowed CRM hostname, and still-live MCP transaction.
- Consume upstream state exactly once. Prefer a Postgres RPC or conditional DELETE ... RETURNING so concurrent callbacks cannot both succeed.
- After upstream token exchange, fetch account identity from amoCRM and upsert encrypted credentials into `amocrm_connections`.
- Create the MCP AuthorizationCode using the original ChatGPT transaction values and the verified account identity as server-controlled subject/context.
- Return the authorization code only to the originally validated ChatGPT redirect URI, preserving its original state and adding no unrelated redirect parameters.
- Keep HTML responses generic and `Cache-Control: no-store`; never render credentials, raw code, raw state, or tokens.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_oauth_account_linking tests.test_oauth_redirect -v`

Expected: all transaction-binding, replay, expiry, and redirect tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_contract tests.test_oauth_account_linking tests.test_oauth_redirect -v`

Expected: existing MCP contract and new OAuth-linking tests pass.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add oauth_backend.py tests/test_oauth_account_linking.py tests/test_oauth_redirect.py supabase/migrations/
git commit -m "feat: bind amoCRM OAuth to MCP authorization"
```

## Task 2: Add grant-scoped token issuance, rotation, and revocation

**Files:**
- Modify: `oauth_backend.py`
- Create: a new Supabase migration under `supabase/migrations/` after live migration reconciliation
- Create: `tests/test_oauth_grants.py`
- Modify: `tests/test_provider_scope.py` only for regression assertions

**Interfaces:**
- Existing: `SupabaseOAuthProvider.exchange_authorization_code(client, authorization_code)`
- Existing: `SupabaseOAuthProvider.exchange_refresh_token(client, refresh_token, scopes)`
- Existing: `SupabaseOAuthProvider.load_access_token(token)`
- Existing: `SupabaseOAuthProvider.revoke_token(token)`
- Produce: `mcp_oauth_grants` table and atomic DB operations for code consumption, token issuance, refresh rotation, and grant revocation.

- [ ] **Step 1: Add focused failing tests**

Test:
- each authorization-code exchange creates a distinct grant bound to the account identity embedded by the verified callback;
- access and refresh token rows share the same grant ID;
- raw MCP token values are never persisted (only SHA-256 hashes);
- the resource, client ID, and scopes survive issuance and refresh;
- wrong client, expired code, and replayed code cannot create a grant;
- concurrent exchange of the same code creates at most one grant;
- refresh rotation preserves grant/account binding and rejects replay;
- revoking one grant revokes its token family without revoking another grant for the same CRM account.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_oauth_grants -v`

Expected: tests fail because current token payloads contain no grant/account binding and code deletion is separate from token issuance.

- [ ] **Step 3: Implement the minimum behavior**

- Add `mcp_oauth_grants` with a UUID primary key, client ID, account ID FK, scopes, creation time, and revocation time.
- Add `grant_id` to `mcp_oauth_tokens`, foreign-key it to grants, and add an index.
- Add a narrowly scoped Postgres RPC that atomically consumes an unexpired authorization code, validates its client and account subject, creates one grant, and inserts hashed access/refresh token rows.
- Add a refresh-rotation RPC that atomically revokes the presented refresh token and inserts the new pair for the same active grant.
- Include `grant_id` in internal token payload/claims. Keep `AccessToken.resource` equal to the canonical MCP resource.
- Ensure `load_access_token` rejects expired/revoked tokens and tokens whose grant is missing/revoked.
- Ensure `revoke_token` revokes the corresponding grant/token family, not all grants for the client or CRM account.
- Use fixed `search_path`, `SECURITY DEFINER`, explicit grants only to `service_role`, and no public/anon/authenticated execution for privileged RPCs.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_oauth_grants -v`

Expected: one-time code consumption, grant scoping, token rotation, and per-grant revocation tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_oauth_grants tests.test_provider_scope tests.test_contract -v`

Expected: grant tests pass and global-provider multi-account guard remains unchanged.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add oauth_backend.py tests/test_oauth_grants.py tests/test_provider_scope.py supabase/migrations/
git commit -m "feat: bind MCP tokens to account grants"
```

## Task 3: Route every CRM operation through the authenticated grant

**Files:**
- Modify: `oauth_backend.py`
- Modify: `server.py`
- Modify: `connection_lifecycle.py` only if a pure helper is needed for grant resolution
- Create: `tests/test_account_grant_scope.py`
- Modify: `tests/test_connection_lifecycle.py`
- Modify: `tests/test_contract.py`

**Interfaces:**
- Existing: `amo_access_token() -> tuple[str, str]`
- Existing: `get_headers() -> tuple[dict, str]`
- Produce: a grant-aware account resolver that obtains the grant ID from `get_access_token()` and returns exactly one active CRM connection.
- Preserve: `ensure_global_provider_scope(connection_count, provider_name)`.

- [ ] **Step 1: Add focused failing tests**

Test:
- authenticated token A always resolves CRM account A even when account B also exists;
- token B resolves only CRM account B;
- no account is selected using MCP session ID;
- no account is selected from model-supplied tool arguments;
- missing auth context, missing grant claim, revoked grant, wrong client, missing connection, and wrong resource all fail closed;
- two grants for the same CRM account both resolve to the same connection;
- global AMOCHAT/ElevenLabs guard still rejects use with multiple CRM connections.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_account_grant_scope -v`

Expected: tests fail because `amo_access_token()` currently resolves via `mcp_account_selections`.

- [ ] **Step 3: Implement the minimum behavior**

- Add a helper that reads `get_access_token()`, extracts the server-issued grant ID, loads an active grant for the same OAuth client, and loads only the grant's account row.
- Change `amo_access_token()` to call that helper; remove fallback to single-account auto-selection and MCP session state.
- Preserve existing encrypted token decryption and atomic amoCRM refresh lock.
- Ensure refresh updates the shared CRM connection row only; it must not change MCP grant ownership.
- Remove account ID parameters from all exposed account-scoped CRM tools if any are present.
- Remove imports and runtime use of `get_mcp_selection_identity`, `get_selected_amocrm_account_id`, and `set_selected_amocrm_account`.
- Keep global provider guard behavior for credentials that are not yet account-scoped.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_account_grant_scope tests.test_provider_scope -v`

Expected: account A/B isolation and the existing global-provider fail-closed guard pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_contract tests.test_mcp_session_scope tests.test_account_grant_scope tests.test_provider_scope -v`

Expected: MCP contract remains valid; session middleware tests continue to pass but no longer influence CRM account selection.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add oauth_backend.py server.py connection_lifecycle.py tests/
git commit -m "refactor: scope CRM calls to authenticated grants"
```

## Task 4: Replace manual account tools with ChatGPT profile and host-managed lifecycle

**Files:**
- Modify: `server.py`
- Modify: `oauth_backend.py`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/test_profile_tool.py`
- Modify: `tests/test_connection_lifecycle.py`
- Modify: `tests/test_contract.py`
- Modify: metadata/contract tests for `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`

**Interfaces:**
- Produce: authenticated read-only `get_profile()` tool marked with `meta={\"openai/profile\": True}`.
- Preserve: MCP SDK `AuthSettings`, `ClientRegistrationOptions`, and provider discovery routes, subject to metadata compatibility tests.

- [ ] **Step 1: Add focused failing tests**

Test:
- `get_profile` requires validated auth context and returns exactly one profile;
- profile ID is stable across reconnects for the same amoCRM account and differs for different account IDs;
- profile output includes only safe display fields and no credentials;
- `get_profile` tool metadata includes `openai/profile: true`;
- legacy `list_amocrm_connections`, `select_amocrm_account`, `get_selected_amocrm_account`, and arbitrary-account `disconnect_amocrm_connection` are absent from the exposed tool list;
- authorization/resource metadata includes the correct issuer, canonical MCP resource, S256, registration/token auth capabilities that the provider actually supports;
- RFC 9207 issuer-support flag is false unless success and all error redirects include exact `iss`.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_profile_tool tests.test_contract -v`

Expected: tests fail because no profile tool exists and manual account-selection tools are exposed.

- [ ] **Step 3: Implement the minimum behavior**

- Add a stable opaque profile-ID helper using a dedicated stable key and immutable CRM account ID; do not expose the raw account ID as the profile ID.
- Add `get_profile` with an empty argument schema, read-only annotations, and `meta={\"openai/profile\": True}`.
- Return a safe profile object with `id`, account display name, and CRM domain; resolve it only from the authenticated grant.
- Remove manual catalogue and account-selection tools from the exposed MCP tool list.
- Replace arbitrary-account disconnect semantics with grant-scoped revocation through the OAuth revocation endpoint. Do not delete a shared CRM connection while another active grant references it.
- Remove `MCP_ADMIN_PASSWORD` and `MCP_AUTH_PASSWORD` from the active configuration and `.env.example`; update README setup instructions.
- Keep the existing DCR route if it is verified compatible. Do not advertise unsupported token endpoint auth methods or RFC 9207 issuer support. Prefer callback-ID-specific ChatGPT redirects until the SDK can add `iss` to both success and error responses.
- Test the actual metadata JSON generated by the installed SDK version, not a hand-written expected shape.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_profile_tool tests.test_contract -v`

Expected: profile metadata and payload tests pass; manual selection tools are no longer exposed.

- [ ] **Step 5: Run the full regression suite**

Run: `python -m unittest discover -s tests -v`

Expected: all existing and new tests pass; existing CRM write guards, webhook security, chat/voice protections, language tools, and global provider scope tests remain green.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add server.py oauth_backend.py .env.example README.md tests/
git commit -m "feat: expose native ChatGPT account profiles"
```

## Pre-implementation checks and unresolved decisions

1. Reconcile live Supabase migration history against repository filenames before creating/applying DDL. Live history reports version `20261101051219`; repository SQL file is `20261101060000_multi_account_registry_and_session_selection.sql`.
2. Confirm the exact FastMCP v1.x metadata output and DCR token-endpoint authentication method supported by the pinned dependency.
3. Decide whether revoking the last active grant deletes local encrypted amoCRM credentials (recommended) or retains them for reconnect convenience. Either choice must not revoke credentials used by another active grant.
4. Global AMOCHAT and ElevenLabs credentials remain process-global and are still blocked for multiple CRM connections. Account-scoping them is a separate project.
5. Do not merge PR #1, deploy a Preview/Production change, or modify Production environment variables without separate authorization.
