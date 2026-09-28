-- supabase/migrations/003_auth_and_rls.sql
-- Roles, profiles, Row Level Security. Run AFTER 001_init.sql and 002_cpi_official.sql.
 
create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text,
  role       text not null default 'analyst' check (role in ('analyst','admin')),
  created_at timestamptz default now()
);
 
create table if not exists public.audit_log (
  id         bigint generated always as identity primary key,
  actor_id   uuid,
  action     text not null,
  detail     jsonb,
  created_at timestamptz default now()
);
 
-- Every new auth user gets a profile with the LOWEST role
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email);
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
 
-- Role lookup used by policies (security definer avoids policy recursion)
create or replace function public.app_role() returns text
language sql stable security definer set search_path = '' as $$
  select role from public.profiles where id = (select auth.uid())
$$;
revoke all on function public.app_role() from public;
grant execute on function public.app_role() to anon, authenticated;
 
-- Turn RLS on for every table
alter table public.profiles         enable row level security;
alter table public.audit_log        enable row level security;
alter table public.routes           enable row level security;
alter table public.fare_quotes      enable row level security;
alter table public.index_values     enable row level security;
alter table public.dgca_monthly_avg enable row level security;
alter table public.scrape_log       enable row level security;
-- cpi_official already has RLS + public read from 002
 
-- Public (Guest) data
create policy public_read_routes on public.routes       for select using (true);
create policy public_read_index  on public.index_values for select using (true);
 
-- Staff data (Analyst + Admin)
create policy staff_read_quotes on public.fare_quotes
  for select using (public.app_role() in ('analyst','admin'));
create policy staff_read_dgca on public.dgca_monthly_avg
  for select using (public.app_role() in ('analyst','admin'));
 
-- Admin-only data
create policy admin_read_scrapelog on public.scrape_log
  for select using (public.app_role() = 'admin');
create policy admin_read_audit on public.audit_log
  for select using (public.app_role() = 'admin');
 
-- Profiles: see your own row; admins see all. No insert/update policy = nobody can self-promote.
create policy own_or_admin_profiles on public.profiles
  for select using (id = (select auth.uid()) or public.app_role() = 'admin');
 
-- Browser-facing roles can never write. Only the backend (service role) writes.
revoke insert, update, delete on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke insert, update, delete on tables from anon, authenticated;
