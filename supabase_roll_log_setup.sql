-- Run once in Supabase: SQL Editor -> New query -> Run
-- Creates the shared campaign dice roll log used by the D&D Character Sheet app.

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