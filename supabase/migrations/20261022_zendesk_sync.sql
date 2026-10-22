-- Zendesk -> NightAgent status sync (app/zendesk_sync.py): what Zendesk last said about each ticket NightAgent
-- logged there. Only adds columns and widens one check; safe to run more than once.
alter table public.ns_tickets add column if not exists zendesk_status text;
alter table public.ns_tickets add column if not exists zendesk_assignee_id bigint;
alter table public.ns_tickets add column if not exists zendesk_assignee_name text;
alter table public.ns_tickets add column if not exists zendesk_updated_at timestamptz;

-- Ticket history written by the sync has source 'zendesk'; the source check didn't allow it.
alter table public.ns_ticket_events drop constraint if exists ns_ticket_events_source_check;
alter table public.ns_ticket_events add constraint ns_ticket_events_source_check
  check (source in ('call', 'scenario', 'demo', 'follow_up', 'zendesk'));
