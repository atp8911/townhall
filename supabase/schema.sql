-- Ejecutar en el SQL Editor de tu proyecto Supabase (https://app.supabase.com -> tu proyecto -> SQL Editor).

create table if not exists convocatorias (
    id uuid primary key default gen_random_uuid(),
    municipio text not null,
    titulo text not null,
    url text not null,
    fecha_publicacion date,
    fecha_detectada timestamptz not null default now(),
    estado text not null default 'Nueva'
        check (estado in ('Nueva', 'Me interesa', 'Descartada', 'Aplicada')),
    constraint convocatorias_municipio_url_key unique (municipio, url)
);

create index if not exists convocatorias_estado_idx on convocatorias (estado);
create index if not exists convocatorias_fecha_detectada_idx on convocatorias (fecha_detectada desc);

-- Row Level Security: el dashboard estático exige iniciar sesión con
-- Supabase Auth antes de poder leer o actualizar filas (ver README, sección
-- "Restringir el acceso con login"). El scraper usa la "service_role key"
-- (secreta, solo en GitHub Actions), que salta RLS por completo para poder
-- insertar filas nuevas.
alter table convocatorias enable row level security;

drop policy if exists "Public read access" on convocatorias;
drop policy if exists "Authenticated read access" on convocatorias;
create policy "Authenticated read access"
    on convocatorias for select
    using (auth.role() = 'authenticated');

drop policy if exists "Public status update" on convocatorias;
drop policy if exists "Authenticated status update" on convocatorias;
create policy "Authenticated status update"
    on convocatorias for update
    using (auth.role() = 'authenticated')
    with check (auth.role() = 'authenticated');

-- RLS por si sola no da acceso: Postgres primero comprueba el GRANT de la
-- tabla y solo despues aplica las politicas RLS para filtrar filas. Sin estos
-- GRANT explicitos, el rol authenticated recibe "permission denied" aunque
-- las politicas de arriba lo permitan.
grant usage on schema public to authenticated, service_role;
grant select, update on convocatorias to authenticated;
grant select, insert, update, delete on convocatorias to service_role;

-- Nota de seguridad: la clave anon sigue embebida en el JS del dashboard (es
-- pública por diseño), pero ya no basta por sí sola: sin una sesión de
-- Supabase Auth válida, el rol efectivo es "anon" y las políticas de arriba
-- lo bloquean. Solo entran quienes tengan una cuenta creada a mano por ti en
-- Authentication -> Users (con el registro público desactivado).
