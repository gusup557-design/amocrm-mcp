# amoCRM MCP Server

MCP (Model Context Protocol) server for amoCRM integration with Claude Desktop and other AI assistants.

## Features

- **Leads** -- list, get, create, update
- **Contacts** -- list, get, create
- **Companies** -- list, get, create
- **Tasks** -- list, create
- **Pipelines** -- list pipelines and stages
- **Users** -- list account users
- **Notes** -- add and read notes on any entity
- **Account** -- get account info

## Prerequisites

- Python 3.10+
- amoCRM account with API access
- Long-lived token from amoCRM integration settings

## Installation

```bash
git clone https://github.com/DocAtWork2026/amocrm-mcp.git
cd amocrm-mcp
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in `AMOCRM_DOMAIN` and `AMOCRM_TOKEN`. Never commit real credentials.

## Claude Desktop Setup

Add this server to `claude_desktop_config.json` using `python` and the path to `server.py`.

## Available Tools

All original upstream tools are preserved: `get_account_info`, `get_leads`, `get_lead`, `create_lead`, `update_lead`, `get_contacts`, `get_contact`, `create_contact`, `get_companies`, `get_company`, `create_company`, `get_tasks`, `create_task`, `get_pipelines`, `get_users`, `add_note`, and `get_notes`.

## Upstream

Based on https://github.com/DocAtWork2026/amocrm-mcp (MIT License). This repository was recreated from the upstream source files. Git commit history was not mirrored by the available GitHub connector.

## License

MIT


## Vercel deployment

This repository exposes the original 17 tools over MCP Streamable HTTP at:

- MCP endpoint: `https://amocrm-mcp-ascan-006.vercel.app/mcp`
- Health check: `https://amocrm-mcp-ascan-006.vercel.app/health`

The `server.py` ASGI application is used by Vercel's Python runtime. The original stdio entry point remains available for local clients.

### Vercel environment variables

Required for CRM API calls:
- `AMOCRM_DOMAIN` — amoCRM subdomain, without protocol.
- `AMOCRM_TOKEN` — long-lived token. Do not commit it.

Optional Supabase connectivity check:
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` (preferred) or `SUPABASE_SERVICE_ROLE_KEY` (legacy)

Supabase keys are server-only. The health endpoint checks access to the existing `amocrm_connections` table without returning any CRM records or credentials.

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
