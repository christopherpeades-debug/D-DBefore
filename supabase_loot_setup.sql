-- Run once in Supabase SQL Editor after campaign_characters setup.
-- Stores DM treasure hoard state for live player looting.

create table if not exists public.campaign_loot (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null unique,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists campaign_loot_campaign_idx
  on public.campaign_loot (campaign_id);

alter table public.campaign_loot enable row level security;

drop policy if exists "campaign_loot_anon_all" on public.campaign_loot;
create policy "campaign_loot_anon_all"
  on public.campaign_loot
  for all
  to anon, authenticated
  using (true)
  with check (true);