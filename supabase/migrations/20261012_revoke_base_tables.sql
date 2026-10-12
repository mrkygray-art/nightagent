-- The first three tables were created before the other ns_ tables started revoking anon and
-- authenticated grants, and schema.sql (rebuilt from the catalog) never had the revoke. RLS with no
-- policies already blocks those roles; this adds the same second layer the later tables have.
-- Safe to run more than once.
revoke all on public.ns_customers from anon, authenticated;
revoke all on public.ns_tickets   from anon, authenticated;
revoke all on public.ns_calls     from anon, authenticated;
