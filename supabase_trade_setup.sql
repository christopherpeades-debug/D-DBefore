-- Run once in Supabase: SQL Editor -> New query -> Run
-- Creates the pending player-to-player trade log used by the D&D Character Sheet app.

create table if not exists public.campaign_pending_trades (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  from_character_id text not null,
  from_player_name text default '',
  from_character_name text default '',
  to_character_id text not null,
  to_player_name text default '',
  to_character_name text default '',
  item jsonb not null default '{}'::jsonb,
  quantity integer not null default 1,
  status text not null default 'pending',
  claimed_by_character_id text,
  claimed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists campaign_pending_trades_campaign_status_idx
  on public.campaign_pending_trades (campaign_id, status, created_at desc);

create index if not exists campaign_pending_trades_from_idx
  on public.campaign_pending_trades (campaign_id, from_character_id);

create index if not exists campaign_pending_trades_to_idx
  on public.campaign_pending_trades (campaign_id, to_character_id);

alter table public.campaign_pending_trades enable row level security;

drop policy if exists "campaign_pending_trades_anon_all" on public.campaign_pending_trades;
create policy "campaign_pending_trades_anon_all"
  on public.campaign_pending_trades
  for all
  to anon, authenticated
  using (true)
  with check (true);