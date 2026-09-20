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

-- Row Level Security: el dashboard estático usa la clave "anon" (pública),
-- así que solo permitimos lectura y actualización de estado desde el cliente.
-- El scraper usa la "service_role key" (secreta, solo en GitHub Actions),
-- que salta RLS por completo para poder insertar filas nuevas.
alter table convocatorias enable row level security;

drop policy if exists "Public read access" on convocatorias;
create policy "Public read access"
    on convocatorias for select
    using (true);

drop policy if exists "Public status update" on convocatorias;
create policy "Public status update"
    on convocatorias for update
    using (true)
    with check (true);

-- RLS por si sola no da acceso: Postgres primero comprueba el GRANT de la
-- tabla y solo despues aplica las politicas RLS para filtrar filas. Sin estos
-- GRANT explicitos, el rol anon recibe "permission denied" aunque las
-- politicas de arriba digan "using (true)".
grant usage on schema public to anon, service_role;
grant select, update on convocatorias to anon;
grant select, insert, update, delete on convocatorias to service_role;

-- Nota de seguridad: como la clave anon queda embebida en el JS del dashboard
-- (es pública por diseño en apps estáticas sin backend), cualquiera con la URL
-- del dashboard podría leer y cambiar el estado de las convocatorias. No hay
-- política de INSERT/DELETE para anon, así que no pueden borrar ni crear filas.
-- Si en el futuro quieres cerrarlo del todo, añade Supabase Auth y cambia
-- "using (true)" por "using (auth.uid() is not null)".
