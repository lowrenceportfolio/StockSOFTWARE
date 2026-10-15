-- Eseguire nel SQL Editor del proprio progetto Supabase.
create table if not exists public.vintdesk_ledgers (
  user_id uuid primary key references auth.users(id) on delete cascade,
  revision bigint not null default 1 check (revision > 0),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz not null default now()
);
alter table public.vintdesk_ledgers enable row level security;
revoke all on public.vintdesk_ledgers from public, anon, authenticated;
grant select, insert, update on public.vintdesk_ledgers to authenticated;
drop policy if exists own_ledger on public.vintdesk_ledgers;
create policy own_ledger on public.vintdesk_ledgers for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create or replace function public.vintdesk_revision() returns trigger
language plpgsql set search_path = '' as $$
begin
  if TG_OP = 'INSERT' then new.revision := 1;
  else new.revision := old.revision + 1;
  end if;
  new.updated_at := now();
  return new;
end;
$$;
drop trigger if exists vintdesk_revision on public.vintdesk_ledgers;
create trigger vintdesk_revision before insert or update on public.vintdesk_ledgers
for each row execute function public.vintdesk_revision();
