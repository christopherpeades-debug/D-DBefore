-- Run once in Supabase: SQL Editor -> New query -> Run
-- DM-shared NPC statblocks pushed from D&D Behind to player character sheets.

create table if not exists public.campaign_shared_followers (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  character_id text not null,
  follower_name text not null default '',
  monster_json jsonb not null default '{}'::jsonb,
  view_data_json jsonb not null default '{}'::jsonb,
  shared_by text default 'DM',
  source_id text default '',
  created_at timestamptz not null default now()
);

create index if not exists campaign_shared_followers_campaign_char_created_idx
  on public.campaign_shared_followers (campaign_id, character_id, created_at desc);

alter table public.campaign_shared_followers enable row level security;

drop policy if exists "campaign_shared_followers_anon_all" on public.campaign_shared_followers;
create policy "campaign_shared_followers_anon_all"
  on public.campaign_shared_followers
  for all
  to anon, authenticated
  using (true)
  with check (true);