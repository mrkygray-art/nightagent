-- Front desk: Sam takes messages for a department or a person, not only service tickets.
-- Additive: one more department (billing) and a few message fields on routing tasks.

alter table public.ns_routing_tasks drop constraint if exists ns_routing_tasks_destination_check;
alter table public.ns_routing_tasks add constraint ns_routing_tasks_destination_check
  check (destination in ('service', 'service_manager', 'account_executive', 'support', 'billing'));

alter table public.ns_routing_tasks
  add column if not exists callback_number  text,
  add column if not exists person_requested text,
  add column if not exists best_time        text,
  add column if not exists voice            text;

-- Messages taken on a call (not tied to a service ticket), newest first, for the board
create index if not exists ns_routing_tasks_messages_idx on public.ns_routing_tasks (created_at desc)
  where source_ticket_id is null and source_conversation_id is not null;
