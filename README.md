# amoCRM MCP Server

MCP (Model Context Protocol) server for amoCRM integration with ChatGPT and other MCP-compatible AI clients.

## Features

- **Leads** -- list, get, create, update
- **Contacts** -- list, get, create
- **Companies** -- list, get, create
- **Tasks** -- list, create
- **Pipelines** -- list pipelines and stages
- **Users** -- list account users
- **Notes** -- add and read notes on any entity
- **Account** -- get account info
- **Salesbot** -- inspect Salesbot configurations
- **Chats** -- inspect talks and chat templates, read Chat API history, and send guarded text messages
- **Custom fields** -- inspect lead/contact/company fields
- **Events** -- read CRM audit events
- **Sources and webhooks** -- inspect channels and webhook subscriptions
- **Calls** -- add completed call records to CRM cards (does not initiate calls)
- **Transcription** -- guarded ElevenLabs Scribe v2 transcription with speaker diarization and RU/KY/KK/UZ locale mapping
- **Voice telephony** -- explicitly confirmed, allowlisted ElevenLabs SIP outbound calls
- **Conversation languages** -- RU/KY/KK/UZ locale profiles and deterministic language preference resolution
- **Catalogs and tags** -- inspect catalog items and entity tags
- **Widgets** -- inspect installed and available widgets
- **Amma AI agents** -- list, inspect, create, update and delete integration-owned agents when the account and integration have the Amma scope

## Prerequisites

- Python 3.10+
- amoCRM account with administrator permission to install the integration
- Supabase project and Vercel project configured with server-side secrets

## Installation

```bash
git clone https://github.com/DocAtWork2026/amocrm-mcp.git
cd amocrm-mcp
pip install -r requirements.txt
```

## Configuration

For local stdio mode, configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `MCP_TOKEN_ENCRYPTION_KEY`. For production, set them as sensitive Vercel environment variables. Connect the CRM through `/connect`; do not use legacy long-lived API tokens.

## Claude Desktop Setup

Add this server to `claude_desktop_config.json` using `python` and the path to `server.py`.

## Available Tools

All original upstream tools are preserved: `get_account_info`, `get_leads`, `get_lead`, `create_lead`, `update_lead`, `get_contacts`, `get_contact`, `create_contact`, `get_companies`, `get_company`, `create_company`, `get_tasks`, `create_task`, `get_pipelines`, `get_users`, `add_note`, and `get_notes`.

## Upstream

Based on https://github.com/DocAtWork2026/amocrm-mcp (MIT License). This repository was recreated from the upstream source files. Git commit history was not mirrored by the available GitHub connector.

## License

MIT


## Vercel deployment

This repository exposes 46 amoCRM MCP tools over MCP Streamable HTTP at:

- MCP endpoint: `https://amocrm-mcp-ascan-006.vercel.app/mcp`
- Health check: `https://amocrm-mcp-ascan-006.vercel.app/health`

The `server.py` ASGI application is used by Vercel's Python runtime. The original stdio entry point remains available for local clients. The MCP server currently exposes 46 tools; all 17 upstream tools remain present.

### Vercel environment variables

Required:
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`
- `MCP_TOKEN_ENCRYPTION_KEY` — 64-character hex AES-256-GCM key
- `MCP_ADMIN_PASSWORD` — owner password for OAuth consent

Optional:
- `AMOCRM_REDIRECT_URI` — defaults to the production callback
- `MCP_ALLOW_WRITE` — defaults to `false`; only set to `true` to enable CRM and Chat API write tools
- `AMOCHAT_SCOPE_ID` and `AMOCHAT_CHANNEL_SECRET` — required for Chat API reads and writes
- `AMOCHAT_BOT_CLIENT_ID`, `AMOCHAT_BOT_REF_ID`, `AMOCHAT_BOT_NAME` — required for outbound bot messages
- `AMOCHAT_BASE_URL` — defaults to `https://amojo.amocrm.ru`
- `ELEVENLABS_API_KEY` — required for Scribe v2 transcription
- `TRANSCRIPTION_ALLOWED_HOSTS` — comma-separated HTTPS host allowlist for call recording URLs
- `MCP_ALLOW_PAID_AI` — defaults to `false`; required to deliberately enable paid AI API operations
- `ELEVENLABS_AGENT_ID` and `ELEVENLABS_PHONE_NUMBER_ID` — required for outbound SIP calls
- `MCP_ALLOW_OUTBOUND_CALLS` — defaults to `false`; outbound calls also require `confirm_call=true`
- `VOICE_CALL_ALLOWED_NUMBERS` — comma-separated E.164 destination allowlist

Supabase and encryption keys are server-only. The health endpoint checks connectivity without returning CRM records or credentials.

### Security notes

- TLS certificate verification is enabled for all outbound amoCRM and Supabase requests.
- Entity types used in note endpoints are allowlisted.
- Secrets must be configured as sensitive Vercel environment variables and must never be committed.


## Remote OAuth deployment

Production MCP endpoint: `https://amocrm-mcp-ascan-006.vercel.app/mcp`

- amoCRM account connection: `https://amocrm-mcp-ascan-006.vercel.app/connect`
- amoCRM callback: `https://amocrm-mcp-ascan-006.vercel.app/oauth/callback`
- amoCRM external integration secrets webhook: `https://amocrm-mcp-ascan-006.vercel.app/oauth/secrets`
- MCP OAuth uses Authorization Code + PKCE, Dynamic Client Registration, persistent Supabase state, and bearer-token validation.
- Owner consent is protected by the sensitive Vercel variable `MCP_ADMIN_PASSWORD`.
- amoCRM credentials and OAuth tokens are encrypted with AES-256-GCM using `MCP_TOKEN_ENCRYPTION_KEY`; MCP bearer tokens are stored as SHA-256 hashes.
- `MCP_ALLOW_WRITE` defaults to `false`. Original write tools remain present, but create/update/note operations are blocked unless the owner deliberately sets this variable to `true`.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` must be available to the Vercel production runtime.

## Conversation language support

MCP tools `get_supported_languages` and `resolve_conversation_language` expose the initial RU/KY/KK/UZ language contract. The resolver accepts short codes and locale tags, prioritizes an explicitly saved contact preference, then an STT/chat provider's detected language, then a configured fallback, and finally Russian. Detection, translation, transcription, and text-to-speech are separate provider integrations and are not enabled by this language foundation.

## Voice telephony

`voice_start_outbound_call` starts an ElevenLabs Conversational AI outbound call over an imported SIP phone number. It is disabled unless `MCP_ALLOW_PAID_AI=true`, `MCP_ALLOW_OUTBOUND_CALLS=true`, the destination is in `VOICE_CALL_ALLOWED_NUMBERS`, and the individual call includes `confirm_call=true`. This is not yet a configured phone service: the ElevenLabs workspace needs an agent and a SIP number imported from a carrier/PBX first.

## Transcription

`transcription_transcribe_audio_url` uses ElevenLabs Scribe v2 for call recordings, with optional speaker diarization, word timestamps, and audio-event tagging. It accepts only HTTPS URLs from `TRANSCRIPTION_ALLOWED_HOSTS`. Scribe v2 documents support for Russian (`rus`), Kyrgyz (`kir`), Kazakh (`kaz`), and Uzbek (`uzb`). Calls are disabled unless `MCP_ALLOW_PAID_AI=true`, and require an `ELEVENLABS_API_KEY`. Original transcript text is returned without automatic translation.

## Chat API

`chat_get_history` reads message history and `chat_send_text_message` sends text messages through amoCRM Chat API. This is a separate signed API: it requires an amoCRM-registered channel, its `scope_id`, and channel secret. The MCP uses the documented `Date`, `Content-MD5`, and HMAC-SHA1 `X-Signature` headers. Outbound writes remain blocked unless `MCP_ALLOW_WRITE=true`. Channel registration must first be requested from amoCRM support; see the [official registration guide](https://www.amocrm.ru/developers/content/chats/chat-start).

## Extended CRM coverage and boundaries

The extended toolset covers CRM account data, leads, contacts, companies, tasks, pipelines, pipeline stages, custom fields, tags, catalogs, catalog elements, events, sources, webhooks, widgets, Salesbot, talks, chat templates, call logging, Amma agent lifecycle management, Chat API history/message tools, Scribe v2 transcription, and guarded SIP outbound calls.

Important platform boundaries:
- The amoCRM REST Calls API records completed calls against CRM cards. It does **not** place or answer telephone calls. Actual telephony requires a provider/widget or a separate telephony API integration.
- AI voice calls require a voice-agent/telephony provider (for example ElevenLabs plus a supported phone/SIP carrier) and separate credentials, phone-number provisioning, and consent/compliance configuration.
- amoCRM Chat API uses its own channel registration, scope IDs, and HMAC signatures. It is separate from the CRM OAuth bearer token; message history and sending require a separately registered chat channel.
- The public Amma Agents API manages agents connected to an MCP endpoint. It does not document a general endpoint to submit arbitrary prompts to amoCRM's internal Amma model and fetch its generated answer. The API has account availability and integration-scope requirements, and a maximum of two agents created by one integration and ten per account.
- The external-integration OAuth button documents `crm` and `notifications` scopes. Amma's separate scope must be granted through the appropriate amoCRM integration setup; adding an undocumented scope to the button is not valid.
- All CRM write tools remain disabled unless `MCP_ALLOW_WRITE=true` is deliberately enabled. Deleting pipelines, agents, widgets, webhooks or fields can be destructive. Field deletion also removes field values.
