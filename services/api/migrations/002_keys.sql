create table if not exists api_keys (
  provider text primary key,
  key_enc text not null,
  updated_at timestamptz default now()
);
