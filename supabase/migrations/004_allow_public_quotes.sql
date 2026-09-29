-- supabase/migrations/004_allow_public_quotes.sql
-- Allow anonymous (Guest) read on public.fare_quotes so operational dashboard charts
-- can query active records without mandatory login, while retaining write restrictions.

create policy if not exists public_read_quotes on public.fare_quotes
  for select using (true);
