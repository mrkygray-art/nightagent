-- Phase 4: Business Impact metrics, counted from the demo's own records in one round trip.
-- Only the server (service role) may call it.

create or replace function public.ns_impact()
returns json
language sql
stable
set search_path = public
as $$
  select json_build_object(
    'tickets',            (select count(*) from ns_tickets),
    'emergencies',        (select count(*) from ns_tickets where priority = 'emergency'),
    'paged',              (select count(*) from ns_tickets where paged_at is not null),
    'live_calls',         (select count(*) from ns_ticket_events where event_type = 'call_received' and source = 'call'),
    'scenario_calls',     (select count(*) from ns_ticket_events where event_type = 'call_received' and source = 'scenario'),
    'follow_ups',         (select count(*) from ns_ticket_events where event_type = 'follow_up_completed'),
    'resolved',           (select count(*) from ns_ticket_events where event_type = 'resolution_confirmed'),
    'reopened',           (select count(*) from ns_ticket_events where event_type = 'ticket_reopened'),
    'escalated',          (select count(*) from ns_ticket_events where event_type = 'ticket_escalated'),
    'new_from_follow_up', (select count(*) from ns_tickets where source_ticket_id is not null),
    'opportunities',      (select count(*) from ns_opportunities),
    'tasks',              (select count(*) from ns_routing_tasks)
  );
$$;

revoke execute on function public.ns_impact() from public, anon, authenticated;
grant execute on function public.ns_impact() to service_role;
