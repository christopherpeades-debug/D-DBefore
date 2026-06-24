-- Run once in Supabase: SQL Editor -> New query -> Run
-- Shared session card images pushed from D&D Behind to player character sheets.

create table if not exists public.campaign_shared_images (
  id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  character_id text not null,
  image_url text not null,
  title text default '',
  card_id text default '',
  shared_by text default 'DM',
  created_at timestamptz not null default now()
);

create index if not exists campaign_shared_images_campaign_char_created_idx
  on public.campaign_shared_images (campaign_id, character_id, created_at desc);

alter table public.campaign_shared_images enable row level security;

drop policy if exists "campaign_shared_images_anon_all" on public.campaign_shared_images;
create policy "campaign_shared_images_anon_all"
  on public.campaign_shared_images
  for all
  to anon, authenticated
  using (true)
  with check (true);