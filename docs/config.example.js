// Copia este archivo como config.js (en la misma carpeta) y rellena tus
// propios valores del proyecto Supabase (Project Settings -> API).
//
// SUPABASE_ANON_KEY es la clave publica ("anon"/"public"), NO la
// service_role. Es seguro que quede visible en el JS del navegador: el
// acceso real esta controlado por las politicas de Row Level Security
// definidas en supabase/schema.sql (solo lectura + actualizar "estado").
window.TOWNHALL_CONFIG = {
    SUPABASE_URL: "https://xxxxxxxxxxxx.supabase.co",
    SUPABASE_ANON_KEY: "eyJ...tu-anon-key...",
};
