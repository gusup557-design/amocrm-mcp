# amoCRM Client Setup MCP Implementation Plan

> **For agentic workers:** Execute task by task in the existing feature branch. Keep the draft PR open.

**Goal:** Turn the existing amoCRM MCP into a reusable toolkit for configuring one client account at a time, verifying the setup, and safely handing the account back.

**Architecture:** Keep one MCP server and no customer business-profile registry. Maintain a persistent OAuth account catalogue for multiple client amoCRM accounts. Select an account per MCP Streamable HTTP session, not through a process-global variable. Connections remain until the operator explicitly disconnects them; the seven-day guarantee date is informational and never expires credentials. Provider secrets remain deployment-side/manual inputs; the server must not expose or log them.

**Tech Stack:** Python 3.12, MCP Python SDK v1.x, Starlette, httpx, Supabase (existing private OAuth persistence), GitHub Actions.

## Global Constraints

- Work only on `feat/chat-voice-language-foundation`; do not merge or push to `main`.
- No production deploy, live CRM mutation, database migration, paid API request, number purchase, or real phone call without a separate explicit approval.
- Preserve all existing CRM tools and upstream coverage; add only the account catalogue/selection tools required for the workflow.
- Multiple connected amoCRM accounts are allowed. Never silently choose between several accounts; selection is explicit and scoped to one MCP session.
- All credential values stay server-side, secrets are never returned or logged.
- CRM writes, outbound messages, paid transcription, and calls remain denied by default and require explicit guards.
- Manual client-side actions must be stated explicitly and checked before handover.

---

### Task 1: Safe one-account-at-a-time connection lifecycle

**Files:**
- Modify: `oauth_backend.py`
- Modify: `server.py`
- Modify: `.env.example`
- Create: `tests/test_connection_lifecycle.py`

**Interfaces:**
- MCP tools: `list_amocrm_connections()`, `disconnect_amocrm_connection(account_id: int, confirm_disconnect: bool = False)`.
- OAuth behavior: a second distinct amoCRM account cannot become active while another account is connected.
- API auth behavior: `amo_access_token()` raises a clear error if more than one connection exists.

- [ ] Add tests for zero, one, and multiple connection rows; require explicit confirmation before disconnect; verify that a second account is rejected rather than silently selected.
- [ ] Run `python -m unittest tests.test_connection_lifecycle -v` and confirm the missing lifecycle behavior fails.
- [ ] Implement the minimum connection-list, explicit disconnect, and single-active-account guards. Do not revoke or mutate the customer's integration inside amoCRM; explain the owner-side uninstall/revoke step separately.
- [ ] Re-run the focused tests, then `python -m unittest discover -s tests -v`.
- [ ] Commit the passing change to the feature branch.

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
- Cleanup removes only the MCP's stored OAuth material for the specified account after explicit confirmation.

- [ ] Add failing tests for required handover checks, incomplete checklists, and explicit disconnect confirmation.
- [ ] Implement a handover report that cannot claim completion when required external-provider checks are unknown or failed.
- [ ] Run `python -m unittest discover -s tests -v`, inspect the final diff, and confirm the GitHub Actions result for the final head commit.
- [ ] Keep PR #1 open and in draft; report preview/deployment status separately from CI.
