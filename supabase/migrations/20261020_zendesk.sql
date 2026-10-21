-- Zendesk: the id of the Zendesk ticket made for each board ticket. Additive only; safe to run more than once.
alter table public.ns_tickets add column if not exists zendesk_ticket_id bigint;
