-- Official MoSPI CPI "Airfare" series (eSankhyiki), used as backtest benchmark.
-- Public government statistics: readable by everyone (incl. Guest), written only by service role.
create table if not exists cpi_official (
  year        int     not null,
  month       int     not null check (month between 1 and 12),
  state       text    not null,                       -- 'All India', 'NCT of Delhi', ...
  sector      text    not null check (sector in ('Rural','Urban','Combined')),
  item_code   text    not null default '07.3.3.1.2.01',
  base_year   int     not null default 2024,
  index_value numeric not null,
  inflation   numeric,                                -- YoY %, only present from Jan 2026
  imputed     boolean not null default false,         -- MoSPI imputation flag (Y/N)
  primary key (year, month, state, sector, item_code)
);

alter table cpi_official enable row level security;
create policy "public_read_cpi" on cpi_official for select using (true);

create index if not exists idx_cpi_lookup on cpi_official (state, sector, year, month);
