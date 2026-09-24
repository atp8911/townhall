const ESTADOS = ["Nueva", "Me interesa", "Descartada", "Aplicada"];
const FECHA_MINIMA_PUBLICACION = "2026-09-01";

// Entes que vigila el scraper. Se listan a mano porque un ente cuya fuente se
// haya roto no tiene ninguna fila en la tabla, y es justo el que hay que ver.
const MUNICIPIOS = [
    "Sant Feliu de Guíxols",
    "Santa Cristina d'Aro",
    "Castell-Platja d'Aro",
    "Calonge i Sant Antoni",
    "Palamós",
    "Llagostera",
    "Vidreres",
    "Consell Comarcal del Baix Empordà",
];

const ALERTA_DIAS = 60;

function diasDesde(fecha) {
    if (!fecha) return null;
    const d = new Date(fecha);
    if (Number.isNaN(d.getTime())) return null;
    return Math.floor((Date.now() - d.getTime()) / 86400000);
}

function estadoClass(estado) {
    return "estado-" + estado.toLowerCase().replace(/\s+/g, "-");
}

function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleDateString("es-ES", { year: "numeric", month: "2-digit", day: "2-digit" });
}

(function main() {
    const cfg = window.TOWNHALL_CONFIG;
    const statusMsg = document.getElementById("status-msg");
    const loginScreen = document.getElementById("login-screen");
    const appEl = document.getElementById("app");
    const loginForm = document.getElementById("login-form");
    const loginEmail = document.getElementById("login-email");
    const loginPassword = document.getElementById("login-password");
    const loginError = document.getElementById("login-error");
    const logoutBtn = document.getElementById("logout-btn");

    if (!cfg || !cfg.SUPABASE_URL || cfg.SUPABASE_URL.includes("xxxxxxxxxxxx")) {
        appEl.style.display = "block";
        statusMsg.textContent =
            "Falta configurar docs/config.js con tu SUPABASE_URL y SUPABASE_ANON_KEY (copia config.example.js).";
        return;
    }

    const supabase = window.supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_ANON_KEY);

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        loginError.textContent = "";
        const submitBtn = loginForm.querySelector("button");
        submitBtn.disabled = true;

        const { error } = await supabase.auth.signInWithPassword({
            email: loginEmail.value.trim(),
            password: loginPassword.value,
        });

        submitBtn.disabled = false;
        if (error) {
            loginError.textContent = "Credenciales incorrectas o cuenta no autorizada.";
        }
    });

    logoutBtn.addEventListener("click", async () => {
        await supabase.auth.signOut();
    });

    supabase.auth.onAuthStateChange((_event, session) => {
        if (session) {
            loginScreen.style.display = "none";
            appEl.style.display = "block";
            loginForm.reset();
            loadData();
        } else {
            appEl.style.display = "none";
            loginScreen.style.display = "flex";
        }
    });

    const tabla = document.getElementById("tabla");
    const tablaBody = document.getElementById("tabla-body");
    const filtroMunicipio = document.getElementById("filtro-municipio");
    const filtroEstado = document.getElementById("filtro-estado");
    const filtroTexto = document.getElementById("filtro-texto");
    const countsEl = document.getElementById("counts");
    const coberturaGrid = document.getElementById("cobertura-grid");
    const coberturaResumen = document.getElementById("cobertura-resumen");

    let allRows = [];

    async function loadData() {
        statusMsg.textContent = "Cargando...";
        const { data, error } = await supabase
            .from("convocatorias")
            .select("*")
            .gte("fecha_publicacion", FECHA_MINIMA_PUBLICACION)
            .order("fecha_publicacion", { ascending: false });

        if (error) {
            statusMsg.textContent = "Error al cargar datos: " + error.message;
            console.error(error);
            return;
        }

        allRows = data || [];
        populateMunicipioFilter(allRows);
        render();
        loadCobertura();
    }

    async function loadCobertura() {
        // Consulta aparte y sin el filtro de FECHA_MINIMA_PUBLICACION: aqui
        // interesa todo el historico para saber cuando publico cada ente por
        // ultima vez.
        const { data, error } = await supabase
            .from("convocatorias")
            .select("municipio, fecha_publicacion")
            .order("fecha_publicacion", { ascending: false })
            .limit(10000);

        if (error) {
            coberturaResumen.textContent = "no se pudo calcular";
            coberturaResumen.className = "cobertura-resumen";
            console.error(error);
            return;
        }

        renderCobertura(data || []);
    }

    function renderCobertura(rows) {
        const porEnte = new Map(
            MUNICIPIOS.map((m) => [m, { municipio: m, total: 0, recientes: 0, ultima: null }])
        );

        for (const r of rows) {
            // Un municipio en la tabla que no este en MUNICIPIOS (renombrado,
            // ente nuevo) se muestra igual en vez de desaparecer del recuento.
            if (!porEnte.has(r.municipio)) {
                porEnte.set(r.municipio, {
                    municipio: r.municipio,
                    total: 0,
                    recientes: 0,
                    ultima: null,
                });
            }
            const ente = porEnte.get(r.municipio);
            ente.total += 1;
            const dias = diasDesde(r.fecha_publicacion);
            if (dias !== null && dias <= ALERTA_DIAS) ente.recientes += 1;
            if (r.fecha_publicacion && (!ente.ultima || r.fecha_publicacion > ente.ultima)) {
                ente.ultima = r.fecha_publicacion;
            }
        }

        const entes = [...porEnte.values()].map((e) => {
            const dias = diasDesde(e.ultima);
            return { ...e, dias, alerta: dias === null || dias > ALERTA_DIAS };
        });

        // Lo que peor pinta tiene, primero.
        entes.sort((a, b) => (b.dias ?? Infinity) - (a.dias ?? Infinity));

        const enAlerta = entes.filter((e) => e.alerta);
        coberturaResumen.textContent = enAlerta.length
            ? `${enAlerta.length} de ${entes.length} sin novedades en ${ALERTA_DIAS} días`
            : `${entes.length} entes al día`;
        coberturaResumen.className =
            "cobertura-resumen" + (enAlerta.length ? " cobertura-resumen-alerta" : "");

        coberturaGrid.innerHTML = "";
        for (const ente of entes) {
            coberturaGrid.appendChild(renderEnte(ente));
        }
    }

    function renderEnte(ente) {
        const card = document.createElement("div");
        card.className = "ente-card" + (ente.alerta ? " ente-alerta" : "");

        const nombre = document.createElement("div");
        nombre.className = "ente-nombre";
        nombre.textContent = ente.municipio;
        card.appendChild(nombre);

        const cifra = document.createElement("div");
        cifra.className = "ente-cifra";
        cifra.textContent = ente.total;
        const sufijo = document.createElement("span");
        sufijo.className = "ente-cifra-sufijo";
        sufijo.textContent = ente.total === 1 ? "convocatoria" : "convocatorias";
        cifra.appendChild(sufijo);
        card.appendChild(cifra);

        const ultima = document.createElement("div");
        ultima.className = "ente-ultima";
        if (ente.ultima === null) {
            ultima.textContent = "Nunca ha publicado nada";
        } else {
            const dias = ente.dias;
            const cuando = dias === 0 ? "hoy" : dias === 1 ? "hace 1 día" : `hace ${dias} días`;
            ultima.textContent = `Última: ${formatDate(ente.ultima)} · ${cuando}`;
        }
        card.appendChild(ultima);

        const recientes = document.createElement("div");
        recientes.className = "ente-recientes";
        recientes.textContent = ente.alerta
            ? `Sin novedades en ${ALERTA_DIAS} días — revisa la fuente`
            : `${ente.recientes} en los últimos ${ALERTA_DIAS} días`;
        card.appendChild(recientes);

        return card;
    }

    function populateMunicipioFilter(rows) {
        const current = filtroMunicipio.value;
        const municipios = [...new Set(rows.map((r) => r.municipio))].sort();
        filtroMunicipio.innerHTML = '<option value="">Todos</option>';
        for (const m of municipios) {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            filtroMunicipio.appendChild(opt);
        }
        filtroMunicipio.value = current;
    }

    function render() {
        const municipio = filtroMunicipio.value;
        const estado = filtroEstado.value;
        const texto = filtroTexto.value.trim().toLowerCase();

        const filtered = allRows.filter((r) => {
            if (municipio && r.municipio !== municipio) return false;
            if (estado && r.estado !== estado) return false;
            if (texto && !r.titulo.toLowerCase().includes(texto)) return false;
            return true;
        });

        renderCounts(filtered);

        if (filtered.length === 0) {
            tabla.style.display = "none";
            statusMsg.textContent = allRows.length === 0
                ? "Todavía no hay convocatorias guardadas. El scraper las irá añadiendo cada día."
                : "No hay convocatorias que coincidan con los filtros.";
            return;
        }

        statusMsg.textContent = "";
        tabla.style.display = "table";
        tablaBody.innerHTML = "";

        for (const row of filtered) {
            tablaBody.appendChild(renderRow(row));
        }
    }

    function renderCounts(rows) {
        const counts = {};
        for (const e of ESTADOS) counts[e] = 0;
        for (const r of rows) counts[r.estado] = (counts[r.estado] || 0) + 1;

        countsEl.innerHTML = "";
        for (const e of ESTADOS) {
            const chip = document.createElement("span");
            chip.className = "chip";
            chip.textContent = `${e}: ${counts[e]}`;
            countsEl.appendChild(chip);
        }
    }

    function renderRow(row) {
        const tr = document.createElement("tr");

        const tdMunicipio = document.createElement("td");
        tdMunicipio.className = "municipio";
        tdMunicipio.textContent = row.municipio;
        tr.appendChild(tdMunicipio);

        const tdTitulo = document.createElement("td");
        tdTitulo.className = "titulo";
        const a = document.createElement("a");
        a.href = row.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = row.titulo;
        tdTitulo.appendChild(a);
        tr.appendChild(tdTitulo);

        const tdPublicado = document.createElement("td");
        tdPublicado.className = "fecha";
        tdPublicado.textContent = formatDate(row.fecha_publicacion);
        tr.appendChild(tdPublicado);

        const tdDetectado = document.createElement("td");
        tdDetectado.className = "fecha";
        tdDetectado.textContent = formatDate(row.fecha_detectada);
        tr.appendChild(tdDetectado);

        const tdEstado = document.createElement("td");
        const select = document.createElement("select");
        select.className = "estado-select " + estadoClass(row.estado);
        for (const e of ESTADOS) {
            const opt = document.createElement("option");
            opt.value = e;
            opt.textContent = e;
            if (e === row.estado) opt.selected = true;
            select.appendChild(opt);
        }
        select.addEventListener("change", () => updateEstado(row, select));
        tdEstado.appendChild(select);
        tr.appendChild(tdEstado);

        return tr;
    }

    async function updateEstado(row, selectEl) {
        const nuevoEstado = selectEl.value;
        const anterior = row.estado;
        selectEl.disabled = true;

        const { error } = await supabase
            .from("convocatorias")
            .update({ estado: nuevoEstado })
            .eq("id", row.id);

        selectEl.disabled = false;

        if (error) {
            alert("No se pudo actualizar el estado: " + error.message);
            selectEl.value = anterior;
            return;
        }

        row.estado = nuevoEstado;
        selectEl.className = "estado-select " + estadoClass(nuevoEstado);
        renderCounts(applyCurrentFilters());
    }

    function applyCurrentFilters() {
        const municipio = filtroMunicipio.value;
        const estado = filtroEstado.value;
        const texto = filtroTexto.value.trim().toLowerCase();
        return allRows.filter((r) => {
            if (municipio && r.municipio !== municipio) return false;
            if (estado && r.estado !== estado) return false;
            if (texto && !r.titulo.toLowerCase().includes(texto)) return false;
            return true;
        });
    }

    filtroMunicipio.addEventListener("change", render);
    filtroEstado.addEventListener("change", render);
    filtroTexto.addEventListener("input", render);
})();
