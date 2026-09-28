-- ============================================================================
-- Migration 001: Core Airiva Data Tables & Constraints (PostgreSQL / Supabase)
-- Schema: public
-- Rules: No RLS policies here (handled in 003_auth_and_rls.sql). No real data/secrets.
-- ============================================================================

-- 1. Routes (Weights for Törnqvist economic aggregation)
create table if not exists public.routes (
  route_code text primary key,
  weight numeric not null,
  updated_at timestamptz default now()
);

-- 2. Fare Quotes (High-frequency scraped flight quotes)
create table if not exists public.fare_quotes (
  id bigint generated always as identity primary key,
  route_code text references public.routes(route_code),
  source text not null,
  carrier text,
  flight_number text,
  travel_date date not null,
  scrape_date date not null,
  scrape_timestamp timestamptz,
  advance_purchase_days int not null,
  fare_class text,
  base_fare numeric,
  taxes_fees numeric,
  total_fare numeric,
  seats_available int,
  sold_out boolean default false,
  is_outlier boolean default false,
  is_duplicate boolean default false,
  created_at timestamptz default now(),
  constraint uq_fare_quotes_dedup unique (
    source,
    flight_number,
    travel_date,
    fare_class,
    advance_purchase_days,
    scrape_date
  )
);

-- 3. Index Values (Törnqvist composite and route-level index series)
create table if not exists public.index_values (
  id bigint generated always as identity primary key,
  date date not null,
  granularity text not null check (granularity in ('daily', 'weekly', 'monthly')),
  route_code text references public.routes(route_code),
  index_value numeric not null,
  constraint uq_index_values unique nulls not distinct (date, granularity, route_code)
);

-- 4. DGCA Monthly Average (Official benchmark comparison data)
create table if not exists public.dgca_monthly_avg (
  route_code text references public.routes(route_code),
  month date not null,
  avg_fare numeric,
  source_doc text,
  primary key (route_code, month)
);

-- 5. Scrape Log (Scraper task audit and monitoring)
create table if not exists public.scrape_log (
  id bigint generated always as identity primary key,
  run_id text,
  source text,
  route_code text,
  advance_window text,
  started_at timestamptz,
  finished_at timestamptz,
  status text,
  records_collected int,
  error text
);

-- ============================================================================
-- Performance Indexes
-- ============================================================================
create index if not exists idx_fare_quotes_route_travel on public.fare_quotes (route_code, travel_date);
create index if not exists idx_fare_quotes_scrape_timestamp on public.fare_quotes (scrape_timestamp);
create index if not exists idx_index_values_lookup on public.index_values (route_code, date, granularity);
create index if not exists idx_scrape_log_source_started on public.scrape_log (source, started_at);
