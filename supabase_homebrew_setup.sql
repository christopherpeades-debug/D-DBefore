-- Run once in Supabase SQL Editor after campaign_characters / campaign_loot setup.
-- Stores DM-authored homebrew features shared with all players in a campaign.

create table if not exists public.campaign_homebrew (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null unique,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists campaign_homebrew_campaign_idx
  on public.campaign_homebrew (campaign_id);

alter table public.campaign_homebrew enable row level security;

drop policy if exists "campaign_homebrew_anon_all" on public.campaign_homebrew;
create policy "campaign_homebrew_anon_all"
  on public.campaign_homebrew
  for all
  to anon, authenticated
  using (true)
  with check (true);