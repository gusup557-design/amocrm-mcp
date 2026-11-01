-- Persistent account catalogue with request/session-scoped account selection.
-- No automatic expiration: guarantee_until is informational only.
ALTER TABLE public.amocrm_connections
    ADD COLUMN IF NOT EXISTS account_name text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS guarantee_until timestamptz;

-- Store hostnames (without a scheme) because the API client adds https:// itself.
-- Also allow modern Kommo domains.
ALTER TABLE public.amocrm_connections
    DROP CONSTRAINT IF EXISTS amocrm_connections_base_domain_check;

ALTER TABLE public.amocrm_connections
    ADD CONSTRAINT amocrm_connections_base_domain_check
    CHECK (
        base_domain ~ '^[A-Za-z0-9][A-Za-z0-9.-]*\.(amocrm\.(ru|com)|kommo\.com)$'
    );

CREATE TABLE IF NOT EXISTS public.mcp_account_selections (
    mcp_principal text NOT NULL,
    mcp_session_id text NOT NULL,
    account_id bigint NOT NULL
        REFERENCES public.amocrm_connections(account_id)
        ON DELETE CASCADE,
    selected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (mcp_principal, mcp_session_id),
    CHECK (length(mcp_principal) BETWEEN 1 AND 255),
    CHECK (length(mcp_session_id) BETWEEN 1 AND 256)
);

CREATE INDEX IF NOT EXISTS mcp_account_selections_account_id_idx
    ON public.mcp_account_selections (account_id);

ALTER TABLE public.mcp_account_selections ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.mcp_account_selections FROM anon, authenticated;
GRANT ALL ON TABLE public.mcp_account_selections TO service_role;

COMMENT ON TABLE public.mcp_account_selections IS
    'MCP session-scoped selected amoCRM account. Contains identifiers only, not credentials.';

COMMENT ON COLUMN public.amocrm_connections.guarantee_until IS
    'Informational end of the 7-day service guarantee. It never expires, disables, or deletes an account connection.';
