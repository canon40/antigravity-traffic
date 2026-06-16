-- Supabase SQL Editor → New query → Run (Agent-HQ / qkporqtajfikppwsishz)
-- publishable(anon) 키로 크롤러 upsert 가 동작하도록 RLS·권한 포함

create table if not exists public.keywords (
    id bigserial primary key,
    created_at timestamptz default now(),
    category text not null,
    keyword text not null,
    monthly_search_volume int default 0,
    competition_index float default 0.0,
    constraint unique_category_keyword unique (category, keyword)
);

create index if not exists idx_keywords_category_volume
    on public.keywords (category, monthly_search_volume desc);

alter table public.keywords enable row level security;

drop policy if exists keywords_select_all on public.keywords;
drop policy if exists keywords_insert_all on public.keywords;
drop policy if exists keywords_update_all on public.keywords;

create policy keywords_select_all on public.keywords
    for select using (true);

create policy keywords_insert_all on public.keywords
    for insert with check (true);

create policy keywords_update_all on public.keywords
    for update using (true) with check (true);

grant usage on schema public to anon, authenticated;
grant select, insert, update on public.keywords to anon, authenticated;
grant usage, select on sequence keywords_id_seq to anon, authenticated;
