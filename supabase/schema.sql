-- NightShift Dispatch tables (prefix ns_), living in the shared Supabase project
-- "Contrator Companies" (sufyfmhqpdarlqtotjla).
-- Reconstructed 2026-10-01 from the live database catalog after the original file was lost.
--
-- Access model: RLS is on with NO policies and no anon/authenticated grants, so only the
-- service role (the FastAPI backend) can read or write. The browser never talks to Supabase.

create table if not exists public.ns_customers (
  customer_id          text primary key,
  business_name        text not null,
  contact_name         text,
  phone_digits         text not null,
  site_address         text,
  systems              text,
  service_plan         text,
  after_hours_coverage boolean not null default false,
  created_at           timestamptz not null default now()
);
create index if not exists ns_customers_phone_idx on public.ns_customers (phone_digits);

create table if not exists public.ns_tickets (
  ticket_id       text primary key,
  customer_id     text references public.ns_customers (customer_id),
  caller_name     text,
  callback_number text,
  issue_summary   text,
  category        text,
  priority        text not null check (priority in ('emergency', 'urgent', 'routine')),
  priority_reason text,
  status          text not null default 'open',
  paged_at        timestamptz,
  conversation_id text,
  created_at      timestamptz not null default now()
);
create index if not exists ns_tickets_created_idx on public.ns_tickets (created_at desc);

create table if not exists public.ns_calls (
  conversation_id text primary key,
  agent_id        text,
  summary         text,
  call_successful text,
  duration_secs   integer,
  transcript      text,
  received_at     timestamptz not null default now()
);

alter table public.ns_customers enable row level security;
alter table public.ns_tickets   enable row level security;
alter table public.ns_calls     enable row level security;

-- Demo customers (same as SEED_CUSTOMERS in app/store.py)
insert into public.ns_customers
  (customer_id, business_name, contact_name, phone_digits, site_address, systems, service_plan, after_hours_coverage)
values
  ('C-1001', 'Sunset Dental Group', 'Maria Lopez', '3105550142', '4100 Demo Ave, Suite 200, Torrance, CA',
   'Bosch intrusion panel, 12 Hanwha cameras, 4-door Acre access control',
   'Gold - 24/7 monitoring and after-hours service', true),
  ('C-1002', 'Westside Self Storage', 'James Carter', '3105550178', '880 Example Blvd, Hawthorne, CA',
   'DMP intrusion panel, 8 Verkada cameras, gate keypad',
   'Standard - business-hours service only', false),
  ('C-1003', 'Harbor Logistics Warehouse', 'Priya Shah', '4245550119', '2200 Sample Way, Carson, CA',
   'Mercury-based access control (24 doors), 40 Axis cameras, Milestone VMS',
   'Platinum - 24/7 monitoring and priority dispatch', true)
on conflict (customer_id) do nothing;
