-- Phase 1: service lifecycle + event history. Additive only; the earlier code keeps working
-- ('open' stays an allowed status for tickets created before the lifecycle existed).

alter table public.ns_tickets
  add column if not exists demo            boolean not null default false,
  add column if not exists scenario        text,
  add column if not exists demo_key_hash   text,
  add column if not exists base_status     text,
  add column if not exists technician_name text;

alter table public.ns_tickets drop constraint if exists ns_tickets_status_check;
alter table public.ns_tickets add constraint ns_tickets_status_check check (status in (
  'open', 'new', 'awaiting_dispatch', 'dispatched', 'technician_assigned', 'en_route', 'onsite',
  'work_completed', 'follow_up_pending', 'resolved', 'reopened', 'escalated', 'closed'
));

create index if not exists ns_tickets_scenario_created_idx
  on public.ns_tickets (created_at desc) where scenario is not null;

-- One row per thing that happened to a ticket. Rows are added, never edited; Demo Mode's
-- Reset deletes only its own simulated rows (source = 'demo').
create table if not exists public.ns_ticket_events (
  id              bigint generated always as identity primary key,
  ticket_id       text not null references public.ns_tickets (ticket_id) on delete cascade,
  event_type      text not null,
  description     text not null default '',
  simulated       boolean not null default false,
  source          text not null default 'call' check (source in ('call', 'scenario', 'demo', 'follow_up')),
  occurred_at     timestamptz not null default now(),
  conversation_id text,
  actor_type      text,
  actor_id        text,
  metadata        jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);
create index if not exists ns_ticket_events_ticket_idx on public.ns_ticket_events (ticket_id, occurred_at, id);

-- Same access model as the other ns_ tables: RLS on, no policies, so only the server's
-- service role can read or write.
alter table public.ns_ticket_events enable row level security;
revoke all on public.ns_ticket_events from anon, authenticated;
