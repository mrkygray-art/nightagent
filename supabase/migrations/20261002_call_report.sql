-- Call report: every tool Sam calls is logged, and the ticket remembers which voice took the call.
-- Additive only.

create table if not exists public.ns_tool_calls (
  id              bigint generated always as identity primary key,
  conversation_id text,
  ticket_id       text references public.ns_tickets (ticket_id) on delete cascade,
  tool            text not null,
  outcome         text not null default '',
  called_at       timestamptz not null default now()
);
create index if not exists ns_tool_calls_conversation_idx on public.ns_tool_calls (conversation_id)
  where conversation_id is not null;
create index if not exists ns_tool_calls_ticket_idx on public.ns_tool_calls (ticket_id)
  where ticket_id is not null;

-- Same access model as the other ns_ tables: RLS on, no policies, server only.
alter table public.ns_tool_calls enable row level security;
revoke all on public.ns_tool_calls from anon, authenticated;

alter table public.ns_tickets add column if not exists voice text;
