-- A caller who reports the same open problem again is added to the existing ticket (event
-- caller_called_again) instead of getting a duplicate. That call still counts as a live call
-- handled, and it no longer counts as "handled without a ticket".

create or replace function public.ns_impact()
returns json
language sql
stable
set search_path = public
as $$
  with front_desk as (
    select conversation_id from ns_tool_calls
    where conversation_id is not null and tool <> 'record_follow_up_outcome'
    group by conversation_id
    having count(ticket_id) = 0
  ),
  without_ticket as (
    select conversation_id from front_desk f
    where not exists (select 1 from ns_tickets t
                      where t.conversation_id = f.conversation_id or t.follow_up_conversation_id = f.conversation_id)
  )
  select json_build_object(
    'tickets',            (select count(*) from ns_tickets),
    'emergencies',        (select count(*) from ns_tickets where priority = 'emergency'),
    'paged',              (select count(*) from ns_tickets where paged_at is not null),
    'live_calls',         (select count(*) from ns_ticket_events
                           where event_type in ('call_received', 'caller_called_again') and source = 'call'),
    'scenario_calls',     (select count(*) from ns_ticket_events where event_type = 'call_received' and source = 'scenario'),
    'follow_ups',         (select count(*) from ns_ticket_events where event_type = 'follow_up_completed'),
    'resolved',           (select count(*) from ns_ticket_events where event_type = 'resolution_confirmed'),
    'reopened',           (select count(*) from ns_ticket_events where event_type = 'ticket_reopened'),
    'escalated',          (select count(*) from ns_ticket_events where event_type = 'ticket_escalated'),
    'new_from_follow_up', (select count(*) from ns_tickets where source_ticket_id is not null),
    'opportunities',      (select count(*) from ns_opportunities),
    'tasks',              (select count(*) from ns_routing_tasks),
    'calls_without_ticket', (select count(*) from without_ticket),
    'specialist_calls',   (select count(distinct conversation_id) from ns_tool_calls
                           where tool in ('billing_lookup', 'request_billing_review', 'record_sales_interest'))
  );
$$;

revoke execute on function public.ns_impact() from public, anon, authenticated;
grant execute on function public.ns_impact() to service_role;
