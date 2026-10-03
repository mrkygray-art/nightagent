-- Calls that joined an open ticket because the same problem was reported again, so the repeat
-- caller's page can show "Your call" on that ticket. Additive only.
alter table public.ns_tickets add column if not exists repeat_conversation_ids text[] not null default '{}';
