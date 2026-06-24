-- Run once in Supabase: SQL Editor -> New query -> Run
-- Creates the shared campaign text chat used by D&D Beside and D&D Behind.

create table if not exists public.campaign_chat_messages (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  character_id text not null default '',
  player_name text default '',
  character_name text default '',
  message_text text not null default '',
  whisper_to_character_id text default '',
  whisper_to_character_name text default '',
  created_at timestamptz not null default now()
);

-- Migration for existing installs (safe to re-run):
alter table public.campaign_chat_messages
  add column if not exists whisper_to_character_id text default '';
alter table public.campaign_chat_messages
  add column if not exists whisper_to_character_name text default '';

create index if not exists campaign_chat_messages_campaign_created_idx
  on public.campaign_chat_messages (campaign_id, created_at desc);

alter table public.campaign_chat_messages enable row level security;

drop policy if exists "campaign_chat_messages_anon_all" on public.campaign_chat_messages;
create policy "campaign_chat_messages_anon_all"
  on public.campaign_chat_messages
  for all
  to anon, authenticated
  using (true)
  with check (true);