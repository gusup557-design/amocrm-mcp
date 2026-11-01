# amoCRM Client Setup MCP Implementation Plan

> **For agentic workers:** Execute task by task in the existing feature branch. Keep the draft PR open.

**Goal:** Turn the existing amoCRM MCP into one universal CRM/communications toolkit plus a dedicated business-setup toolkit. Keep several client OAuth connections in a durable account catalogue without creating customer business profiles; select exactly one account per MCP session, configure it, hand it back, and keep the connection until the operator manually disconnects it.

**Architecture:** Keep one MCP server and no customer business-profile registry. Maintain a persistent OAuth account catalogue for multiple client amoCRM accounts. Select an account per MCP Streamable HTTP session, not through a process-global variable. Connections remain until the operator explicitly disconnects them; the seven-day guarantee date is informational and never expires credentials. Provider secrets remain deployment-side/manual inputs; the server must not expose or log them.

**Tech Stack:** Python 3.12, MCP Python SDK v1.x, Starlette, httpx, Supabase (existing private OAuth persistence), GitHub Actions.

## Global Constraints

- Work only on `feat/chat-voice-language-foundation`; do not merge or push to `main`.
- No production deploy, live CRM mutation, database migration, paid API request, number purchase, or real phone call without a separate explicit approval.
- Preserve all existing CRM tools and upstream coverage; add only the account catalogue/selection tools required for the workflow.
- Multiple connected amoCRM accounts are allowed. Never silently choose between several accounts; selection is explicit and scoped to one MCP session.
- All credential values stay server-side, secrets are never returned or logged.
- Provider credentials still stored as global environment variables must be fail-closed when multiple CRM accounts are connected; they must not leak across account selection. This guard currently covers Chat API, ElevenLabs transcription/calls, post-call preview and signed provider webhooks.
- CRM writes, outbound messages, paid transcription, and calls remain denied by default and require explicit guards.
- Manual client-side actions must be stated explicitly and checked before handover.

---

### Task 1: Persistent multi-account catalogue and session-scoped selection

**Files:**
- Modify: `oauth_backend.py`
- Modify: `server.py`
- Modify: `connection_lifecycle.py`
- Create: `mcp_session_scope.py`
- Create: `supabase/migrations/20261101060000_multi_account_registry_and_session_selection.sql`
- Create/update: lifecycle and session-isolation tests

**Interfaces:**
- MCP tools: `list_amocrm_connections()`, `select_amocrm_account(account_id)`, `get_selected_amocrm_account()`, `disconnect_amocrm_connection(account_id, confirm_disconnect=false)`.
- OAuth callback stores each account independently; the account catalogue has no automatic expiry or deletion.
- `guarantee_until` is informational only and does not disable or remove a connection.
- `amo_access_token()` resolves the selected account by authenticated MCP principal plus Streamable HTTP session ID.
- If several accounts exist and a session has no selection, CRM tools fail closed and request explicit selection.
- Deleting an account cascades its session selections but does not revoke the amoCRM-side integration.

- [x] Add tests for zero/one/multiple connections, explicit selection, stale selections, guarantee-date independence, secret-free catalogue output, explicit disconnect and concurrent session isolation.
- [x] Implement per-session account selection without a process-global mutable active-account variable.
- [x] Remove the previous single-account connection rejection from the OAuth callback.
- [x] Add the Supabase migration for catalogue metadata, base-domain validation and private session selections; keep it unapplied until explicit database-change approval.
- [x] Keep PR #1 open/draft and leave `main` and Production unchanged.

### Task 2: Setup audit, client onboarding blueprint, and provider capability catalogue

**Files:**
- Create: `provisioning.py`
- Modify: `server.py`
- Modify: `README.md`
- Create: `tests/test_provisioning.py`

**Interfaces:**
- Pure functions: `get_provider_catalog()`, `build_client_setup_plan(business_type, telephony_provider, requested_channels)`, `validate_sip_endpoint(host, port, transport)`.
- MCP tools: `get_amocrm_setup_report()`, `get_client_setup_plan(...)`, `get_telephony_provider_guide(provider)`, `validate_sip_endpoint_settings(host, port, transport)`.
- The audit returns per-endpoint success/failure and counts, not complete contact/customer records.

- [ ] Add focused failing tests for known provider names, unknown providers, manual-vs-API steps, SIP host/port/transport validation, and setup plan composition.
- [ ] Run the focused tests and record expected failures.
- [ ] Implement only evidence-backed capability labels. Zadarma, Mango Office, Asterisk/ARI, and ElevenLabs must distinguish documented API actions from manual portal/SIP configuration. Do not claim generic SIP is an API-managed provider.
- [ ] Add read-only CRM readiness checks using existing v4 endpoints; partial failures must be reported per section without hiding other results.
- [ ] Re-run focused and full test suites.
- [ ] Document provider prerequisites, manual owner actions, and security limits; commit the passing change.

### Task 3: Provider adapters and integration diagnostics

**Files:**
- Create: `telephony_providers/` modules only for providers whose official API contracts are verified.
- Modify: `server.py`, `requirements.txt` only when a pinned dependency is necessary.
- Create: focused provider adapter tests.

**Interfaces:**
- Read-only credential/configuration status checks.
- Provider-specific API clients that accept credentials at runtime or from server-side environment variables, never returning the secret.
- Dry-run configuration previews before any provider-side write.

- [ ] Research current official API contracts for each selected provider.
- [ ] Add request-signing, timeout, TLS, response-validation, and secret-redaction tests before implementing API operations.
- [ ] Implement read-only diagnostics first. Keep number purchase, account billing changes, outbound calls, and routing changes behind explicit action confirmation.
- [ ] Run adapter tests and full suite; document providers that remain manual-only.

### Task 4: Handover, access cleanup, and release verification

**Files:**
- Modify: `server.py`, `README.md`
- Create: `tests/test_handover.py`

**Interfaces:**
- MCP tool: `get_client_handover_checklist(...)`.
- Checklist separates MCP-local credentials from client-owned integrations that must remain active.
- Cleanup removes only the MCP's stored OAuth material for the specified account after explicit confirmation. There is no seven-day auto-disconnect; an optional guarantee date is informational.

- [ ] Add failing tests for required handover checks, incomplete checklists, and explicit disconnect confirmation.
- [ ] Implement a handover report that cannot claim completion when required external-provider checks are unknown or failed.
- [ ] Run `python -m unittest discover -s tests -v`, inspect the final diff, and confirm the GitHub Actions result for the final head commit.
- [ ] Keep PR #1 open and in draft; report preview/deployment status separately from CI.
