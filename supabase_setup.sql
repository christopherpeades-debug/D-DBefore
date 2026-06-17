-- Run once in Supabase: SQL Editor -> New query -> Run
-- Creates the shared campaign character table used by the D&D Character Sheet app.

create table if not exists public.campaign_characters (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  character_id text not null,
  player_name text default '',
  character_name text default '',
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (campaign_id, character_id)
);

create index if not exists campaign_characters_campaign_idx
  on public.campaign_characters (campaign_id);

alter table public.campaign_characters enable row level security;

drop policy if exists "campaign_characters_anon_all" on public.campaign_characters;
create policy "campaign_characters_anon_all"
  on public.campaign_characters
  for all
  to anon, authenticated
  using (true)
  with check (true);

-- GM treasure hoard table (D&D Behind loot sync)
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

-- Shared campaign dice roll log (local roller popup mode)
create table if not exists public.campaign_dice_rolls (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  character_id text not null default '',
  player_name text default '',
  character_name text default '',
  roll_label text default '',
  roll_formula text default '',
  roll_result text default '',
  roll_detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists campaign_dice_rolls_campaign_created_idx
  on public.campaign_dice_rolls (campaign_id, created_at desc);

alter table public.campaign_dice_rolls enable row level security;

drop policy if exists "campaign_dice_rolls_anon_all" on public.campaign_dice_rolls;
create policy "campaign_dice_rolls_anon_all"
  on public.campaign_dice_rolls
  for all
  to anon, authenticated
  using (true)
  with check (true);

-- Security note: keep your campaign_id secret like a room password.
-- Anyone with your Supabase anon key and campaign_id can read/write that campaign.