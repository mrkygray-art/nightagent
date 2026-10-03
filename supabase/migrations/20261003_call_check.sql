-- Call check: grade each call. Additive only.
-- ns_calls caches ElevenLabs' post-call analysis (so the page doesn't ask ElevenLabs on every refresh)
-- and the voice for calls that ended without a ticket or message.
alter table public.ns_calls
  add column if not exists voice        text,
  add column if not exists eval_status  text,
  add column if not exists evaluation   jsonb,
  add column if not exists evaluated_at timestamptz;

-- What the AI suggested, next to the priority our rules set, so the check can compare them.
alter table public.ns_tickets add column if not exists suggested_priority text;
