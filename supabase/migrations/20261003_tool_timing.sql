-- Engineering Mode: how long each tool call took on our server. Additive only.
alter table public.ns_tool_calls add column if not exists duration_ms integer;
