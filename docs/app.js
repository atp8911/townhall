const ESTADOS = ["Nueva", "Me interesa", "Descartada", "Aplicada"];

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

    if (!cfg || !cfg.SUPABASE_URL || cfg.SUPABASE_URL.includes("xxxxxxxxxxxx")) {
        statusMsg.textContent =
            "Falta configurar docs/config.js con tu SUPABASE_URL y SUPABASE_ANON_KEY (copia config.example.js).";
        return;
    }

    const supabase = window.supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_ANON_KEY);

    const tabla = document.getElementById("tabla");
    const tablaBody = document.getElementById("tabla-body");
    const filtroMunicipio = document.getElementById("filtro-municipio");
    const filtroEstado = document.getElementById("filtro-estado");
    const filtroTexto = document.getElementById("filtro-texto");
    const countsEl = document.getElementById("counts");

    let allRows = [];

    async function loadData() {
        statusMsg.textContent = "Cargando...";
        const { data, error } = await supabase
            .from("convocatorias")
            .select("*")
            .order("fecha_publicacion", { ascending: false });

        if (error) {
            statusMsg.textContent = "Error al cargar datos: " + error.message;
            console.error(error);
            return;
        }

        allRows = data || [];
        populateMunicipioFilter(allRows);
        render();
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

    loadData();
})();
