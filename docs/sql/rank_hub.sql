-- 나눔랩 SEO 허브: 24시간 순위 추적 (Supabase SQL Editor에서 실행)
-- Vercel 환경변수: SUPABASE_URL, SUPABASE_SERVICE_KEY (또는 ANON_KEY)

create table if not exists public.rank_history (
  id bigserial primary key,
  recorded_at text not null,
  keyword text not null,
  store_name text,
  rank integer not null default 999,
  prev_rank text,
  change text default '-',
  task_type text,
  detail text,
  created_at timestamptz default now()
);

create index if not exists rank_history_recorded_at_idx on public.rank_history (recorded_at);
create index if not exists rank_history_keyword_idx on public.rank_history (keyword);

create table if not exists public.rank_hub_state (
  id integer primary key default 1,
  auto_enabled boolean not null default true,
  last_cron_at timestamptz,
  last_report jsonb,
  logs jsonb default '[]'::jsonb,
  updated_at timestamptz default now()
);

insert into public.rank_hub_state (id, auto_enabled)
values (1, true)
on conflict (id) do nothing;

alter table public.rank_hub_state
  add column if not exists last_traffic_at timestamptz;

-- RLS: 서비스 롤 키 사용 시 우회. anon 키만 쓸 경우 정책 추가 필요.
alter table public.rank_history enable row level security;
alter table public.rank_hub_state enable row level security;

create policy "rank_history_service_all"
  on public.rank_history for all
  using (true) with check (true);

create policy "rank_hub_state_service_all"
  on public.rank_hub_state for all
  using (true) with check (true);
