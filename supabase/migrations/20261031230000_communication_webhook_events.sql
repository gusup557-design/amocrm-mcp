-- Communication webhook inbox. Private service-role access only.
-- Raw payloads may contain customer PII and call transcripts.
create table if not exists public.communication_webhook_events (
    id uuid primary key default gen_random_uuid(),
    provider text not null check (provider in ('amocrm_chat', 'elevenlabs')),
    event_id text not null,
    event_type text not null,
    conversation_id text,
    raw_payload jsonb not null,
    processing_status text not null default 'received'
        check (processing_status in ('received', 'processing', 'processed', 'failed')),
    processing_error text,
    received_at timestamptz not null default now(),
    processed_at timestamptz,
    unique (provider, event_id)
);

create index if not exists communication_webhook_events_status_received_idx
    on public.communication_webhook_events (processing_status, received_at);

create index if not exists communication_webhook_events_conversation_idx
    on public.communication_webhook_events (conversation_id)
    where conversation_id is not null;

alter table public.communication_webhook_events enable row level security;

revoke all on table public.communication_webhook_events from anon, authenticated;
grant all on table public.communication_webhook_events to service_role;

comment on table public.communication_webhook_events is
    'Private, idempotent inbox for signed amoCRM Chat API and ElevenLabs webhooks. Raw payloads may contain personal data; accessible only to service_role.';
