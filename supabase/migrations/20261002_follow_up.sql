-- Phase 2: follow-up call outcomes, routing tasks, and sales opportunities. Additive only.

alter table public.ns_tickets
  add column if not exists source_ticket_id          text references public.ns_tickets (ticket_id) on delete set null,
  add column if not exists follow_up_token_hash      text,
  add column if not exists follow_up_started_at      timestamptz,
  add column if not exists follow_up_conversation_id text,
  add column if not exists resolution                text,
  add column if not exists csat                      smallint check (csat between 1 and 5);

create index if not exists ns_tickets_follow_up_token_idx on public.ns_tickets (follow_up_token_hash)
  where follow_up_token_hash is not null;
create index if not exists ns_tickets_follow_up_started_idx on public.ns_tickets (follow_up_started_at desc)
  where follow_up_started_at is not null;
create index if not exists ns_tickets_source_idx on public.ns_tickets (source_ticket_id)
  where source_ticket_id is not null;

-- Work handed to a person: a service callback, a manager escalation, an AE follow-up...
create table if not exists public.ns_routing_tasks (
  task_id                text primary key,
  destination            text not null check (destination in
                           ('service', 'service_manager', 'account_executive', 'support')),
  assigned_to            text not null,
  customer_id            text references public.ns_customers (customer_id),
  contact_name           text,
  site_address           text,
  source_ticket_id       text references public.ns_tickets (ticket_id) on delete cascade,
  source_conversation_id text,
  reason                 text not null,
  summary                text not null default '',
  priority               text not null check (priority in ('high', 'normal')),
  requested_follow_up    text,
  status                 text not null default 'open',
  demo                   boolean not null default false,
  created_at             timestamptz not null default now()
);
create index if not exists ns_routing_tasks_source_idx on public.ns_routing_tasks (source_ticket_id);

-- Sales leads found on a service call. Value is never invented: it's what the customer said, or TBD.
create table if not exists public.ns_opportunities (
  opportunity_id         text primary key,
  customer_id            text references public.ns_customers (customer_id),
  contact_name           text,
  site_address           text,
  source_ticket_id       text references public.ns_tickets (ticket_id) on delete cascade,
  source_conversation_id text,
  type                   text not null,
  scope                  text,
  interest               text,
  device_count           text,
  timeline               text,
  estimated_value        text not null,
  assigned_to            text not null,
  status                 text not null default 'new',
  demo                   boolean not null default false,
  created_at             timestamptz not null default now()
);
create index if not exists ns_opportunities_source_idx on public.ns_opportunities (source_ticket_id);

alter table public.ns_ticket_events drop constraint if exists ns_ticket_events_source_check;
alter table public.ns_ticket_events add constraint ns_ticket_events_source_check
  check (source in ('call', 'scenario', 'demo', 'follow_up'));

alter table public.ns_routing_tasks enable row level security;
alter table public.ns_opportunities enable row level security;
revoke all on public.ns_routing_tasks from anon, authenticated;
revoke all on public.ns_opportunities from anon, authenticated;
