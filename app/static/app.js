"use strict";
/* Vialidad · interfaz web (JS sin framework). Todo texto de usuario se escapa con esc(). */

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "America/Guayaquil";
const CLASES = {
  pothole: { n: "Bache / daño mayor", c: "#dc2626" },
  alligator_crack: { n: "Piel de cocodrilo", c: "#ea580c" },
  transverse_crack: { n: "Grieta transversal", c: "#2563eb" },
  longitudinal_crack: { n: "Grieta longitudinal", c: "#0d9488" },
};
const CAL_CLASS = { "Bueno": "b-Bueno", "Regular": "b-Regular", "Malo": "b-Malo", "Muy malo": "b-Muy" };
const CAL_COLOR = { "Bueno": "#16a34a", "Regular": "#ca8a04", "Malo": "#ea580c", "Muy malo": "#dc2626" };
const ORIGEN = { exif: "EXIF de la foto", manual: "ingresada a mano", subida: "momento de la subida" };
const VIEWS = { panel: "Panel", analizar: "Analizar fotos", seguimiento: "Seguimiento", tramos: "Tramos" };

const nombreClase = (k) => CLASES[k]?.n ?? k;
const badge = (cal) => `<span class="badge ${CAL_CLASS[cal] || ""}">${esc(cal)}</span>`;
const fmtDT = (iso) => new Date(iso).toLocaleString("es-EC", { timeZone: TZ, dateStyle: "medium", timeStyle: "short" });
const fmtDay = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("es-EC", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" });
const dayNum = (d) => Date.parse(d + "T00:00:00Z") / 86400000;
const chips = (conteo) => Object.entries(conteo || {}).map(([k, n]) => `<span class="chip"><i style="background:${CLASES[k]?.c || "#888"}"></i>${esc(nombreClase(k))}: <b>${n}</b></span>`).join("") || '<span class="hint">Sin daños detectados</span>';

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}

function fmtDetail(d) {
  if (!d) return "";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join(" · ");
  return JSON.stringify(d);
}

async function api(path, opts) {
  let r;
  try { r = await fetch(path, opts); } catch { throw new Error("No se pudo conectar con el servidor."); }
  if (r.status === 204) return null;
  let j = null;
  try { j = await r.json(); } catch { /* sin cuerpo JSON */ }
  if (!r.ok) throw new Error(fmtDetail(j?.detail) || `Error ${r.status}`);
  return j;
}

/* ---------------- navegación ---------------- */
let current = null;
function route() {
  const v = (location.hash || "#panel").slice(1);
  const view = VIEWS[v] ? v : "panel";
  if (view === current) return;
  current = view;
  document.querySelectorAll(".view").forEach((s) => (s.hidden = s.id !== "v-" + view));
  document.querySelectorAll(".side nav a").forEach((a) => a.classList.toggle("on", a.dataset.view === view));
  $("#title").textContent = VIEWS[view];
  document.title = `${VIEWS[view]} · Vialidad`;
  $("#side").classList.remove("open");
  ({ panel: loadPanel, analizar: loadAnalizar, seguimiento: loadSeguimiento, tramos: loadTramos })[view]();
}
window.addEventListener("hashchange", route);
$("#burger").onclick = () => $("#side").classList.toggle("open");

/* ---------------- estado del servidor ---------------- */
async function refreshStatus() {
  const box = $("#status"), txt = $("#status-txt");
  try {
    const h = await api("/api/health");
    if (!h.db) { box.className = "status bad"; txt.textContent = "Base de datos sin conexión"; }
    else if (!h.modelo_cargado) { box.className = "status warn"; txt.textContent = "Modelo aún sin cargar"; }
    else { box.className = "status ok"; txt.textContent = "Sistema operativo"; }
    $("#model-ver").textContent = h.modelo_cargado ? "Modelo: " + h.modelo_version : "";
  } catch { box.className = "status bad"; txt.textContent = "Sin conexión al servidor"; }
}

/* ---------------- panel ---------------- */
let map, markersLayer, chClases;
async function loadPanel() {
  let r;
  try { r = await api("/api/resumen"); } catch (e) { return toast(e.message, "err"); }
  $("#kpis").innerHTML = [
    ["Tramos", r.tramos, "en seguimiento"],
    ["Capturas", r.capturas, `fotos · ${r.videos} video(s)`],
    ["Daños detectados", r.detecciones, "en total"],
    ["Índice medio", r.indice_medio ?? "—", "0 = sin daños · 100 = crítico"],
  ].map(([a, b, c]) => `<div class="kpi"><span>${a}</span><b>${b}</b><em>${c}</em></div>`).join("");

  // dona por tipo de daño
  const keys = Object.keys(CLASES);
  const data = keys.map((k) => r.por_clase[k] || 0);
  chClases?.destroy();
  chClases = new Chart($("#ch-clases"), {
    type: "doughnut",
    data: { labels: keys.map(nombreClase), datasets: [{ data, backgroundColor: keys.map((k) => CLASES[k].c), borderWidth: 2, borderColor: "#fff" }] },
    options: { maintainAspectRatio: false, cutout: "58%", plugins: { legend: { position: "right", labels: { boxWidth: 12, font: { size: 12 } } } } },
  });

  // barras por calificación
  const total = r.capturas || 1;
  $("#calif-bars").innerHTML = ["Bueno", "Regular", "Malo", "Muy malo"].map((c) => {
    const n = r.por_calificacion[c] || 0;
    return `<div class="cbar"><span>${badge(c)}</span><div class="tr"><i style="width:${(n / total) * 100}%;background:${CAL_COLOR[c]}"></i></div><b>${n}</b></div>`;
  }).join("");

  // mapa
  if (!map) {
    map = L.map("map", { scrollWheelZoom: true }).setView([-3.26, -79.96], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; colaboradores de OpenStreetMap" }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
  }
  markersLayer.clearLayers();
  const pts = [];
  r.marcadores.forEach((m) => {
    const mk = L.circleMarker([m.lat, m.lon], { radius: 9, color: "#fff", weight: 2, fillColor: CAL_COLOR[m.calificacion] || "#64748b", fillOpacity: 0.95 });
    mk.bindPopup(`<b>${esc(m.tramo)}</b><br>${esc(fmtDT(m.fecha))}<br>Índice ${m.indice} · ${esc(m.calificacion)}<br><a href="#" data-cap="${m.id}">Ver captura</a>`);
    mk.addTo(markersLayer);
    pts.push([m.lat, m.lon]);
  });
  setTimeout(() => { map.invalidateSize(); if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 16 }); }, 50);
  $("#map-hint").textContent = pts.length ? `${pts.length} captura(s) con ubicación.` : "Aún no hay capturas con GPS. Ingresa latitud/longitud al analizar o usa fotos que conserven su EXIF.";

  $("#recientes").innerHTML = r.recientes.length ? tablaCapturas(r.recientes) : '<div class="empty">Todavía no hay capturas. Empieza en “Analizar fotos”.</div>';
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-cap]");
  if (a) { e.preventDefault(); openCaptura(+a.dataset.cap); }
  const tr = e.target.closest("tr[data-cap]");
  if (tr) openCaptura(+tr.dataset.cap);
  const tv = e.target.closest("tr[data-vid]");
  if (tv) openVideo(+tv.dataset.vid);
  const tl = e.target.closest(".tl[data-cap]");
  if (tl) openCaptura(+tl.dataset.cap);
});

function tablaCapturas(list) {
  return `<table><thead><tr><th></th><th>Tramo</th><th>Fecha</th><th>Índice</th><th>Calificación</th><th>Daños</th></tr></thead><tbody>` +
    list.map((c) => `<tr class="click" data-cap="${c.id}"><td><img class="th" loading="lazy" src="${esc(c.url_anotada)}" alt=""></td>
      <td><b>${esc(c.tramo_nombre)}</b></td><td>${esc(fmtDT(c.fecha_captura))}</td><td><b>${c.indice_severidad.toFixed(1)}</b></td>
      <td>${badge(c.calificacion)}</td><td>${c.n_detecciones}</td></tr>`).join("") + "</tbody></table>";
}

/* ---------------- gráficos compartidos ---------------- */
const bandsPlugin = {
  id: "bands",
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea: a, scales: { y } } = chart;
    ctx.save();
    [[0, 15, "#dcfce7"], [15, 35, "#fef9c3"], [35, 60, "#ffedd5"], [60, 100, "#fee2e2"]].forEach(([lo, hi, col]) => {
      ctx.fillStyle = col; const t = y.getPixelForValue(hi), b = y.getPixelForValue(lo);
      ctx.fillRect(a.left, t, a.right - a.left, b - t);
    });
    ctx.restore();
  },
};
const fmtT = (s) => { const m = Math.floor(s / 60), r = Math.round(s % 60); return `${m}:${String(r).padStart(2, "0")}`; };
const fmtMB = (b) => (b / 1048576).toFixed(1) + " MB";

/* ---------------- analizar ---------------- */
let files = [];
let CFG = { foto_mb: 15, video_mb: 500, video_max_frames: 300, video_max_frames_cap: 6000, ms_por_imagen: null,
  perfiles: { normal: { conf: 0.25, conf_clase: {} }, sensible: { conf: 0.1, conf_clase: {} } } };
const registro = new Map();
let regId = 0;
const reg = (c) => { registro.set(++regId, c); return regId; };
const umbralTxt = (p) => { const v = Object.values(p.conf_clase || {}); return v.length ? `${Math.min(...v)}–${Math.max(...v)}` : String(p.conf); };
const fmtDur = (s) => s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1).replace(".", ",")} h`;
const vmodo = () => $("input[name=vmodo]:checked").value;
const modo = () => ({ tipo: $("input[name=tipo]:checked").value, destino: $("input[name=destino]:checked").value });

function updateForm(limpiar) {
  const { tipo, destino } = modo();
  const video = tipo === "video", guardar = destino === "guardar";
  $("#campos-guardar").hidden = !guardar;
  $("#gps-box").hidden = video;
  $("#video-opts").hidden = !video;
  $("#file").accept = video ? ".mp4,.mov,.avi,.mkv,.webm,.m4v,video/*" : "image/jpeg,image/png,image/webp";
  $("#file").multiple = !video;
  $("#drop-titulo").textContent = video ? "Arrastra un video aquí o haz clic" : "Arrastra fotos aquí o haz clic";
  $("#drop-sub").textContent = video ? `MP4, MOV, AVI, MKV o WEBM · máx. ${CFG.video_mb} MB · un video a la vez` : `JPG, PNG o WEBP · máx. ${CFG.foto_mb} MB por foto`;
  $("#lbl-fecha").textContent = video ? "Fecha y hora de inicio del video" : "Fecha y hora de la foto";
  $("#fecha-hint").textContent = video ? "Si lo dejas vacío se usa el momento de la subida." : "Si lo dejas vacío se usa la fecha EXIF de la foto o, si no la tiene, el momento de la subida.";
  $("#destino-hint").textContent = guardar ? "Se guarda el resultado y las imágenes para comparar en el tiempo." : "Solo verás el resultado. No se guarda nada en la base de datos ni en disco.";
  $("#btn-send").textContent = video ? "Analizar video" : "Analizar";
  const anot = vmodo() === "anotado";
  const conGpx = video && $("#f-gpx").files.length > 0;
  $("#gpx-opts").hidden = !conGpx;
  $("#l-fecha-gpx").hidden = guardar;
  $("#l-intervalo").hidden = anot;
  $("#l-cadan").hidden = !anot;
  $("#vmodo-hint").textContent = anot
    ? "Devuelve el video con los daños dibujados y un rótulo con el índice. Tarda más: se procesa en el servidor, no en tiempo real."
    : "Analiza un fotograma cada cierto tiempo y entrega gráfica y los fotogramas más críticos. Es la opción rápida.";
  const mf = $("#f-maxfr");
  mf.max = CFG.video_max_frames_cap;
  if (!mf.value) mf.value = CFG.video_max_frames;
  const ms = CFG.ms_por_imagen;
  $("#maxfr-hint").textContent = `Máximo ${CFG.video_max_frames_cap}. Si el video da más, se espacian los análisis para respetarlo.` +
    (ms ? ` En este equipo cada fotograma tarda ≈${Math.round(ms)} ms: ${mf.value || CFG.video_max_frames} fotogramas ≈ ${fmtDur((mf.value || CFG.video_max_frames) * ms / 1000)}.` : "");
  const o = $("#f-sens").options;
  o[0].textContent = `Normal · umbral ${umbralTxt(CFG.perfiles.normal)}`;
  o[1].textContent = `Sensible · umbral ${umbralTxt(CFG.perfiles.sensible)}`;
  $("#sens-hint").textContent = $("#f-sens").value === "sensible"
    ? "Detecta más daños leves o dudosos, pero también más falsas alarmas. El índice saldrá más alto: no lo compares con capturas analizadas en «Normal»."
    : "Equilibrada: menos falsas alarmas, pero puede pasar por alto daños leves.";
  if (limpiar) { files = []; renderPreviews(); }
}
document.querySelectorAll("input[name=tipo]").forEach((i) => (i.onchange = () => updateForm(true)));
document.querySelectorAll("input[name=destino]").forEach((i) => (i.onchange = () => updateForm(false)));
$("#f-sens").onchange = () => updateForm(false);
document.querySelectorAll("input[name=vmodo]").forEach((i) => (i.onchange = () => updateForm(false)));
$("#f-maxfr").oninput = () => updateForm(false);
$("#f-gpx").onchange = () => updateForm(false);

function fillLegend() {
  $("#legend").innerHTML = Object.values(CLASES).map((c) => `<span class="chip"><i style="background:${c.c}"></i>${c.n}</span>`).join("");
}
async function cargarSelectTramos(sel, keep) {
  const ts = await api("/api/tramos");
  const prev = keep ?? sel.value;
  sel.innerHTML = ts.map((t) => `<option value="${t.id}">${esc(t.nombre)}${t.ciudad ? " · " + esc(t.ciudad) : ""}</option>`).join("");
  if (prev && ts.some((t) => String(t.id) === String(prev))) sel.value = prev;
  return ts;
}
async function loadAnalizar() {
  fillLegend();
  try { CFG = await api("/api/config"); } catch { /* se usan los valores por defecto */ }
  updateForm(false);
  try {
    const ts = await cargarSelectTramos($("#f-tramo"));
    $("#no-tramos").hidden = ts.length > 0;
  } catch (e) { toast(e.message, "err"); }
}
function renderPreviews() {
  const box = $("#previews");
  box.innerHTML = "";
  files.forEach((f, i) => {
    const d = document.createElement("div");
    if (modo().tipo === "video") {
      d.className = "vfile";
      d.innerHTML = `🎬 <b>${esc(f.name)}</b> <small>${fmtMB(f.size)}</small>`;
    } else {
      const img = document.createElement("img");
      img.src = URL.createObjectURL(f); img.alt = f.name; img.title = f.name;
      img.onload = () => URL.revokeObjectURL(img.src);
      d.append(img);
    }
    const b = document.createElement("button");
    b.type = "button"; b.textContent = "✕"; b.title = "Quitar";
    b.onclick = () => { files.splice(i, 1); renderPreviews(); };
    d.append(b); box.append(d);
  });
}
function addFiles(list) {
  const video = modo().tipo === "video";
  for (const f of list) {
    const ok = video ? /^video\//.test(f.type) || /\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(f.name) : /^image\/(jpeg|png|webp)$/.test(f.type);
    if (!ok) { toast(`“${f.name}” no es un ${video ? "video compatible" : "JPG, PNG o WEBP"}.`, "err"); continue; }
    if (video) files = [f]; else files.push(f);
  }
  renderPreviews();
}
$("#file").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#file").click(); } });

$("#btn-geo").onclick = () => {
  if (!navigator.geolocation) return toast("Tu navegador no soporta geolocalización.", "err");
  navigator.geolocation.getCurrentPosition(
    (p) => { $("#f-lat").value = p.coords.latitude.toFixed(6); $("#f-lon").value = p.coords.longitude.toFixed(6); toast("Ubicación cargada.", "ok"); },
    () => toast("No se pudo obtener la ubicación (revisa los permisos del navegador).", "err"),
    { enableHighAccuracy: true, timeout: 10000 });
};

$("#form-an").onsubmit = async (e) => {
  e.preventDefault();
  const { tipo, destino } = modo();
  if (!files.length) return toast(tipo === "video" ? "Agrega un video." : "Agrega al menos una foto.", "err");
  const guardar = destino === "guardar";
  if (guardar && !$("#f-tramo").value) return toast("Elige un tramo (o créalo en «Tramos»).", "err");
  const lat = $("#f-lat").value.trim(), lon = $("#f-lon").value.trim();
  if (tipo === "foto" && guardar && !!lat !== !!lon) return toast("Indica latitud y longitud juntas.", "err");
  const btn = $("#btn-send");
  btn.disabled = true;
  $("#an-empty").hidden = true;
  try {
    if (tipo === "video") await analizarVideo(files[0], guardar);
    else await analizarFotos(guardar, lat, lon);
  } finally {
    btn.disabled = false;
    $("#btn-send").textContent = tipo === "video" ? "Analizar video" : "Analizar";
  }
};

async function analizarFotos(guardar, lat, lon) {
  const queue = files.slice();
  const box = $("#an-results");
  const btn = $("#btn-send");
  let ok = 0;
  for (let i = 0; i < queue.length; i++) {
    btn.innerHTML = `<span class="spin"></span> Analizando ${i + 1} de ${queue.length}…`;
    const fd = new FormData();
    fd.append("file", queue[i]);
    fd.append("sensibilidad", $("#f-sens").value);
    let c;
    try {
      if (guardar) {
        fd.append("tramo_id", $("#f-tramo").value);
        if ($("#f-fecha").value) fd.append("fecha_captura", $("#f-fecha").value);
        if (lat) { fd.append("lat", lat); fd.append("lon", lon); }
        if ($("#f-notas").value.trim()) fd.append("notas", $("#f-notas").value.trim());
        c = await api("/api/capturas", { method: "POST", body: fd });
      } else {
        const r = await api("/api/analizar", { method: "POST", body: fd });
        c = {
          id: null, solo: true, tramo_nombre: "Sin guardar", archivo_original: r.archivo,
          url_anotada: r.imagen_anotada, url_imagen: r.imagen_original, ancho: r.ancho, alto: r.alto,
          fecha_captura: r.fecha_exif, origen_fecha: r.fecha_exif ? "exif" : null,
          lat: r.gps_exif?.lat ?? null, lon: r.gps_exif?.lon ?? null, origen_gps: r.gps_exif ? "exif" : null,
          indice_severidad: r.indice_severidad, calificacion: r.calificacion, conteo: r.conteo,
          n_detecciones: r.n_detecciones, detecciones: r.detecciones, tiempo_inferencia_ms: r.tiempo_inferencia_ms,
          conf_umbral: r.conf_umbral, perfil: r.perfil, modelo_version: r.modelo_version, notas: null,
        };
      }
      const holder = document.createElement("div");
      holder.innerHTML = resultadoHTML(c);
      box.prepend(holder.firstElementChild);
      ok++;
      files = files.filter((f) => f !== queue[i]);
      renderPreviews();
    } catch (err) {
      const holder = document.createElement("div");
      holder.innerHTML = `<div class="res"><div class="info err"><b>${esc(queue[i].name)}</b><br>No se pudo analizar: ${esc(err.message)}</div></div>`;
      box.prepend(holder.firstElementChild);
    }
  }
  if (ok) toast(guardar ? `${ok} foto(s) analizada(s) y guardada(s).` : `${ok} foto(s) analizada(s). No se guardó nada.`, "ok");
}

function resultadoHTML(c) {
  const k = reg(c);
  const gps = c.lat != null ? `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)} (${c.origen_gps === "exif" ? "EXIF" : "manual"})` : "—";
  const fecha = c.fecha_captura ? `${esc(fmtDT(c.fecha_captura))} <small>(${ORIGEN[c.origen_fecha] || ""})</small>` : "—";
  return `<div class="res">
    <img src="${esc(c.url_anotada)}" alt="Foto con daños marcados" onclick="abrirRegistro(${k})">
    <div class="info">
      <b>${esc(c.tramo_nombre)}</b> ${c.solo ? '<span class="badge b-solo">no guardado</span>' : ""}
      <div class="gauge"><div class="v">${c.indice_severidad.toFixed(1)}<small> / 100</small></div>
        <div class="meter"><i style="left:${Math.min(100, c.indice_severidad)}%"></i></div>${badge(c.calificacion)}</div>
      <div class="stack">${chips(c.conteo)}</div>
      <dl><dt>Fecha</dt><dd>${fecha}</dd>
        <dt>GPS</dt><dd>${esc(gps)}</dd>
        <dt>Sensibilidad</dt><dd>${esc(c.perfil)} · umbral ${c.conf_umbral}</dd>
        <dt>Análisis</dt><dd>${Math.round(c.tiempo_inferencia_ms)} ms</dd></dl>
      <button class="btn ghost sm" onclick="abrirRegistro(${k})">Ver detalle</button>
      <button class="btn ghost sm" onclick="descargarCaptura(registro.get(${k}), this)">⬇ Descargar análisis</button>
    </div></div>`;
}
window.abrirRegistro = (k) => { const c = registro.get(k); if (c) { if (c.id) openCaptura(c.id); else showCaptura(c); } };

/* ---- video: subida con progreso + seguimiento del trabajo ---- */
function xhrJson(path, fd, onprog, holder) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    holder.xhr = x;
    x.open("POST", path);
    x.upload.onprogress = (e) => e.lengthComputable && onprog(e.loaded / e.total);
    x.onload = () => {
      let j = null;
      try { j = JSON.parse(x.responseText); } catch { /* sin JSON */ }
      if (x.status >= 200 && x.status < 300) resolve(j);
      else reject(new Error(fmtDetail(j?.detail) || `Error ${x.status}`));
    };
    x.onerror = () => reject(new Error("No se pudo conectar con el servidor."));
    x.onabort = () => reject(new Error("Cancelado."));
    x.send(fd);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function analizarVideo(file, guardar) {
  const box = $("#an-results");
  const card = document.createElement("div");
  card.className = "prog";
  card.innerHTML = `<b>${esc(file.name)}</b> <small>${fmtMB(file.size)}</small>
    <div class="pb"><i style="width:0%"></i></div><div class="hint" data-msg>Subiendo video…</div>
    <button type="button" class="btn ghost sm" data-cancel>Cancelar</button>`;
  box.prepend(card);
  const bar = $(".pb i", card), pb = $(".pb", card), msg = $("[data-msg]", card);
  const st = { xhr: null, job: null, cancel: false };
  $("[data-cancel]", card).onclick = async () => {
    st.cancel = true; msg.textContent = "Cancelando…";
    if (st.job) { try { await api("/api/videos/jobs/" + st.job, { method: "DELETE" }); } catch { /* ya terminó */ } }
    else st.xhr?.abort();
  };
  const fd = new FormData();
  fd.append("file", file);
  fd.append("sensibilidad", $("#f-sens").value);
  const mf = parseInt($("#f-maxfr").value, 10);
  if (!(mf >= 1 && mf <= CFG.video_max_frames_cap)) { card.remove(); return toast(`El límite de fotogramas debe estar entre 1 y ${CFG.video_max_frames_cap}.`, "err"); }
  const gpx = $("#f-gpx").files[0];
  const fechaIni = guardar ? $("#f-fecha").value : $("#f-fecha-gpx").value;
  if (gpx) {
    if (!fechaIni) { card.remove(); return toast("Con un GPX indica la fecha y hora de inicio del video.", "err"); }
    fd.append("gpx", gpx); fd.append("desfase_s", $("#f-desfase").value || "0");
    if (!guardar) fd.append("fecha_inicio", fechaIni);
  }
  fd.append("modo", vmodo());
  fd.append("intervalo_s", $("#f-intervalo").value);
  fd.append("cada_n", $("#f-cadan").value);
  fd.append("max_frames", String(mf));
  fd.append("guardar", guardar ? "true" : "false");
  if (guardar) {
    fd.append("tramo_id", $("#f-tramo").value);
    if ($("#f-fecha").value) fd.append("fecha_inicio", $("#f-fecha").value);
    if ($("#f-notas").value.trim()) fd.append("notas", $("#f-notas").value.trim());
  }
  try {
    const { job_id } = await xhrJson("/api/videos", fd, (p) => { bar.style.width = (p * 100).toFixed(0) + "%"; msg.textContent = `Subiendo video… ${(p * 100).toFixed(0)}%`; }, st);
    st.job = job_id;
    bar.style.width = "0%"; msg.textContent = "En cola…";
    for (;;) {
      await sleep(900);
      const j = await api("/api/videos/jobs/" + job_id);
      if (j.estado === "procesando" || j.estado === "en_cola") {
        if (j.progreso != null) { pb.classList.remove("ind"); bar.style.width = (j.progreso * 100).toFixed(0) + "%"; 
          const eta = j.hechos > 2 && j.transcurrido_s > 3 ? ` · faltan ≈${fmtDur(j.transcurrido_s / j.hechos * (j.total - j.hechos))}` : "";
          msg.textContent = `Analizando fotograma ${j.hechos} de ${j.total}${eta}…`; }
        else { pb.classList.add("ind"); msg.textContent = `Analizando… ${j.hechos} fotogramas`; }
      } else if (j.estado === "listo") {
        const cont = document.createElement("div");
        card.replaceWith(cont);   // primero en el DOM: el mapa necesita medir su contenedor
        renderVideo(cont, j.resultado);
        toast(guardar ? "Video analizado y guardado." : "Video analizado. No se guardó nada.", "ok");
        return;
      } else if (j.estado === "cancelado") { card.innerHTML = `<b>${esc(file.name)}</b><div class="hint">Análisis cancelado.</div>`; return; }
      else throw new Error(j.error || "Error al analizar el video.");
    }
  } catch (err) {
    card.innerHTML = `<b>${esc(file.name)}</b><div class="info err" style="color:var(--muy);margin-top:6px">${esc(st.cancel ? "Análisis cancelado." : "No se pudo analizar: " + err.message)}</div>`;
  }
}

/* ---- resultado de video (también se usa en el detalle guardado) ---- */
let videoCharts = [];
function renderVideo(cont, res) {
  const r = res.resumen, id = "vc" + Math.random().toString(36).slice(2, 8);
  const avisos = [];
  const anot = r.modo === "anotado";
  let umbral = r.conf_umbral;
  if (umbral == null && r.parametros) { try { umbral = umbralTxt(JSON.parse(r.parametros)); } catch { /* sin parámetros */ } }
  if (r.limite_aplicado) avisos.push(anot
    ? `El video es largo: se analizó 1 de cada ${r.cada_n} fotogramas (pedido: 1 de cada ${r.cada_n_pedido}) para no pasar de ${r.max_frames} análisis. Sube el límite si quieres más detalle.`
    : `El video es largo: el intervalo se amplió a ${r.intervalo_s} s para no pasar de ${r.max_frames} fotogramas. Sube el límite si quieres más detalle.`);
  if (r.fps_asumido) avisos.push("El video no indica sus fotogramas por segundo; se asumieron 30, así que los tiempos son aproximados.");
  const pedido = r.intervalo_pedido_s ?? r.intervalo_s;
  const galeria = res.mejores.length ? res.mejores.map((m) => `<figure><img src="${esc(m.imagen)}" alt="Fotograma ${fmtT(m.t)}" onclick="lightbox(this.src)">
      <figcaption><span><b>${fmtT(m.t)}</b> · índice <b>${m.indice.toFixed(1)}</b></span><span>${chips(m.conteo)}</span></figcaption></figure>`).join("")
    : '<p class="hint">Ningún fotograma tuvo daños detectados con esta sensibilidad.</p>';
  cont.innerHTML = `<div class="vres">
    <h3>🎬 ${esc(r.archivo)}</h3>
    <small>${res.guardado ? `Guardado en el seguimiento${res.video_id ? " (video n.º " + res.video_id + ")" : ""}${r.tramo_nombre ? " · " + esc(r.tramo_nombre) : ""}` : "No guardado: este resultado desaparece al recargar la página"}</small>
    ${res.video_url ? `<video class="vplayer" src="${esc(res.video_url)}" controls preload="metadata" playsinline></video>
      <a class="btn ghost sm" href="${esc(res.video_url)}" download="anotado.mp4">⬇ Descargar video anotado</a>
      ${res.guardado ? "" : '<small class="hint"> El archivo es temporal: descárgalo antes de recargar la página.</small>'}` : ""}
    <div class="vact"><button type="button" class="btn primary sm" data-zip>⬇ Descargar análisis (ZIP)</button>
      <small class="hint">Incluye informe, datos (CSV/JSON), fotogramas marcados${anot ? ", imágenes de cada daño" : ""}${res.ruta ? " y la ruta" : ""}.</small></div>
    <div class="vkpis">
      <div><span>Calificación</span><b>${badge(r.calificacion)}</b></div>
      <div><span>Índice medio</span><b>${r.indice_medio.toFixed(1)}</b></div>
      <div><span>Índice máximo</span><b>${r.indice_max.toFixed(1)}</b></div>
      <div><span>Con daños</span><b>${r.pct_afectados.toFixed(0)}%</b></div>
      <div><span>Duración</span><b>${fmtT(r.duracion_s)}</b></div>
      <div><span>Analizados</span><b>${r.n_frames}</b></div>
      ${anot ? '<div><span>Baches (estimado)</span><b data-kpi-baches>–</b></div>' : ""}
    </div>
    <div data-hallazgos></div><div data-mapa></div>
    <h4 style="margin:6px 0 0;font-size:14px">Índice de severidad a lo largo del video</h4>
    <div class="vchart"><canvas id="${id}"></canvas></div>
    <p class="note">${anot ? `Se analizó 1 de cada ${r.cada_n ?? "?"} fotogramas (≈ cada ${r.intervalo_s} s); en el video, las cajas se repiten entre análisis` : `Se analizó 1 fotograma cada ${r.intervalo_s} s (pedido: ${pedido} s)`} con sensibilidad <b>${esc(r.perfil)}</b> (umbral ${esc(String(umbral ?? "—"))}) en ${r.tiempo_proceso_s} s.
      “Con daños” es el % de fotogramas con índice ≥ 15.
      ${anot ? "El <b>conteo de daños es estimado</b> (seguimiento entre fotogramas) y se puede corregir descartando falsas alarmas." : "<b>Este modo no cuenta baches</b>: con un fotograma cada cierto tiempo no se puede saber si dos detecciones son el mismo daño; usa «Video con baches marcados» para una estimación."}
      ${res.ruta ? "La ubicación sale del GPX sincronizado con la hora de inicio que indicaste." : "Sin GPX no hay ubicación: el recorrido se identifica por el tramo y la hora."}</p>
    ${avisos.map((a) => `<p class="warn">${esc(a)}</p>`).join("")}
    <h4 style="margin:16px 0 0;font-size:14px">Fotogramas más críticos</h4>
    <div class="gal">${galeria}</div></div>`;
  $("[data-zip]", cont).onclick = (e) => descargarVideo(res, e.currentTarget);
  if (anot) montarHallazgos(cont, res);
  if (res.ruta?.length > 1 || (res.hallazgos || []).some((h) => h.lat != null) || (res.mejores || []).some((m) => m.lat != null)) { try { montarMapa(cont, res); } catch (e) { $("[data-mapa]", cont).innerHTML = '<p class="hint">No se pudo dibujar el mapa.</p>'; } }
  const pts = res.serie.map((m) => ({ x: m.t, y: m.indice }));
  videoCharts.push(new Chart($("#" + id, cont), {
    type: "line", plugins: [bandsPlugin],
    data: { datasets: [{ label: "Índice", data: pts, borderColor: "#0f172a", backgroundColor: "#0f172a", pointRadius: pts.length > 80 ? 0 : 3, borderWidth: 2, tension: 0 }] },
    options: {
      maintainAspectRatio: false, parsing: false, animation: false,
      scales: { x: { type: "linear", min: 0, ticks: { callback: (v) => fmtT(v), maxTicksLimit: 10 }, title: { display: true, text: "Minuto:segundo del video" }, grid: { display: false } },
        y: { min: 0, max: 100, title: { display: true, text: "Índice" } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it) => "Minuto " + fmtT(it[0].parsed.x), label: (it) => `Índice ${it.parsed.y.toFixed(1)}` } } },
    },
  }));
}

/* ---- conteo estimado de daños + mapa de la ruta ---- */
let videoMaps = [];
const baches = (res) => (res.hallazgos || []).filter((h) => !h.descartado && h.clase === "pothole").length;
function montarHallazgos(cont, res) {
  const box = $("[data-hallazgos]", cont), hs = res.hallazgos || [];
  const linkLoc = (h) => (h.lat != null ? ` <a href="https://www.openstreetmap.org/?mlat=${h.lat}&mlon=${h.lon}#map=19/${h.lat}/${h.lon}" target="_blank" rel="noopener" title="Ver ubicación">📍</a>` : "");
  box.innerHTML = `<details class="hall"><summary><b>Daños distintos estimados: <span data-total></span></b> <span data-chips class="stack"></span></summary>
    <p class="note">Conteo <b>estimado</b> por seguimiento entre fotogramas: un mismo daño se cuenta una sola vez, pero puede unirse mal con otro cercano o partirse en dos.
      Revisa cada imagen y pulsa ✕ para descartar las falsas alarmas: el conteo baja y el informe descargado lo respeta.${res.hallazgos_truncado ? " Se muestran solo los 400 más claros." : ""}
      ${res.guardado ? "Los descartes se guardan." : "Este resultado no está guardado: los descartes valen solo para esta pantalla y la descarga."}</p>
    <div class="hgrid">${hs.length ? hs.map((h, i) => `<figure class="hc" data-i="${i}"><button type="button" class="hx" title="Descartar este daño">✕</button>
      <img loading="lazy" src="${esc(h.imagen)}" alt="${esc(nombreClase(h.clase))}" title="Ir a este momento del video">
      <figcaption><span class="chip"><i style="background:${CLASES[h.clase]?.c || "#888"}"></i>${esc(nombreClase(h.clase))}</span> <b>${fmtT(h.t_ini)}</b>${linkLoc(h)}
        <small>visto en ${h.n_apariciones} análisis · confianza ${(h.conf_max * 100).toFixed(0)}%</small></figcaption></figure>`).join("") : '<p class="hint">No se encontró ningún daño que se repita entre fotogramas.</p>'}</div></details>`;
  const refrescar = () => {
    const c = {}; hs.forEach((h) => { if (!h.descartado) c[h.clase] = (c[h.clase] || 0) + 1; });
    $("[data-total]", box).textContent = hs.filter((h) => !h.descartado).length;
    $("[data-chips]", box).innerHTML = Object.entries(c).map(([k, n]) => `<span class="chip"><i style="background:${CLASES[k]?.c || "#888"}"></i>${esc(nombreClase(k))}: <b>${n}</b></span>`).join("");
    const kb = $("[data-kpi-baches]", cont); if (kb) kb.textContent = baches(res);
    hs.forEach((h, i) => $(`.hc[data-i="${i}"]`, box)?.classList.toggle("off", !!h.descartado));
    cont._mapa?.();
  };
  box.addEventListener("click", async (e) => {
    const fig = e.target.closest(".hc"); if (!fig) return;
    const h = hs[+fig.dataset.i];
    if (e.target.closest(".hx")) {
      const nuevo = !h.descartado;
      if (res.guardado) {
        try { await api(`/api/videos/${res.video_id}/hallazgos/${h.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ descartado: nuevo }) }); }
        catch (err) { return toast(err.message, "err"); }
      }
      h.descartado = nuevo; refrescar();
    } else if (e.target.tagName === "IMG") {
      const v = $("video", cont); if (v) { v.currentTime = Math.max(0, h.t_ini - 0.5); v.scrollIntoView({ behavior: "smooth", block: "center" }); v.play().catch(() => {}); }
    }
  });
  box.querySelectorAll(".hx").forEach((b) => { const h = hs[+b.closest(".hc").dataset.i]; b.title = "Descartar este daño (pulsa otra vez para restaurarlo)"; });
  refrescar();
}
function montarMapa(cont, res) {
  const box = $("[data-mapa]", cont);
  box.innerHTML = '<h4 style="margin:16px 0 6px;font-size:14px">Ruta y ubicación de los daños</h4><div class="vmap"></div><p class="note">Necesita internet para los mosaicos de OpenStreetMap. La ubicación depende de que el reloj del video y el del GPX coincidan.</p>';
  const el = $(".vmap", box);
  if (typeof L === "undefined") { el.textContent = "El mapa no está disponible."; return; }
  const map = L.map(el).setView([-3.26, -79.96], 12), capa = L.layerGroup().addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  videoMaps.push(map);
  const ll = [];
  if (res.ruta?.length > 1) { L.polyline(res.ruta, { color: "#0f172a", weight: 3, opacity: 0.7 }).addTo(map); ll.push(...res.ruta); }
  const dibujar = () => {
    capa.clearLayers();
    (res.hallazgos || []).filter((h) => !h.descartado && h.lat != null).forEach((h) => L.circleMarker([h.lat, h.lon], { radius: 7, color: "#fff", weight: 2, fillColor: CLASES[h.clase]?.c || "#888", fillOpacity: 0.95 })
      .bindTooltip(`${nombreClase(h.clase)} · ${fmtT(h.t_ini)}`).addTo(capa));
    (res.mejores || []).filter((m) => m.lat != null).forEach((m) => L.circleMarker([m.lat, m.lon], { radius: 5, color: "#7c3aed", weight: 2, fillColor: "#a78bfa", fillOpacity: 0.9 })
      .bindTooltip(`Fotograma crítico ${fmtT(m.t)} · índice ${m.indice.toFixed(1)}`).addTo(capa));
  };
  dibujar(); cont._mapa = dibujar;
  (res.hallazgos || []).forEach((h) => h.lat != null && ll.push([h.lat, h.lon]));
  (res.mejores || []).forEach((m) => m.lat != null && ll.push([m.lat, m.lon]));
  if (ll.length) map.fitBounds(L.latLngBounds(ll).pad(0.15));
  setTimeout(() => map.invalidateSize(), 200);
}

/* ---------------- detalle (modal) ---------------- */
function closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; videoCharts.forEach((c) => c.destroy()); videoCharts = []; videoMaps.forEach((m) => m.remove()); videoMaps = []; }
$("#modal-x").onclick = closeModal;
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
window.lightbox = (src) => { $("#modal-body").innerHTML = `<img src="${esc(src)}" alt="" style="width:100%;border-radius:10px;display:block">`; $("#modal").hidden = false; };

async function openCaptura(id) {
  let c;
  try { c = await api("/api/capturas/" + id); } catch (e) { return toast(e.message, "err"); }
  showCaptura(c);
}
function showCaptura(c) {
  const gps = c.lat != null ? `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)} (${c.origen_gps === "exif" ? "EXIF" : "manual"})` : "—";
  const fecha = c.fecha_captura ? `${esc(fmtDT(c.fecha_captura))} <small>(${ORIGEN[c.origen_fecha] || ""})</small>` : "—";
  const filas = c.detecciones.map((d) => `<tr><td><span class="chip"><i style="background:${CLASES[d.clase]?.c || "#888"}"></i>${esc(nombreClase(d.clase))}</span></td><td>${(d.confianza * 100).toFixed(0)}%</td><td>${(d.area_frac * 100).toFixed(1)}%</td></tr>`).join("");
  $("#modal-body").innerHTML = `
    <div class="tabs"><button class="on" data-t="a">Con detecciones</button><button data-t="o">Original</button></div>
    <div class="res">
      <img id="m-img" src="${esc(c.url_anotada)}" alt="Captura" style="cursor:default">
      <div class="info">
        <b>${esc(c.tramo_nombre)}</b> ${c.solo ? '<span class="badge b-solo">no guardado</span>' : ""}
        <div class="gauge"><div class="v">${c.indice_severidad.toFixed(1)}<small> / 100</small></div>
          <div class="meter"><i style="left:${Math.min(100, c.indice_severidad)}%"></i></div>${badge(c.calificacion)}</div>
        <dl><dt>Fecha</dt><dd>${fecha}</dd>
          <dt>GPS</dt><dd>${esc(gps)}</dd><dt>Archivo</dt><dd>${esc(c.archivo_original)}</dd>
          <dt>Tamaño</dt><dd>${c.ancho}×${c.alto} px</dd>
          <dt>Sensibilidad</dt><dd>${esc(c.perfil)} · umbral ${c.conf_umbral}</dd>
          <dt>Modelo</dt><dd>${esc(c.modelo_version)}</dd>
          <dt>Análisis</dt><dd>${Math.round(c.tiempo_inferencia_ms)} ms</dd>
          ${c.notas ? `<dt>Notas</dt><dd>${esc(c.notas)}</dd>` : ""}</dl>
        ${filas ? `<table style="margin-top:12px"><thead><tr><th>Daño</th><th>Conf.</th><th>% imagen</th></tr></thead><tbody>${filas}</tbody></table>` : '<p class="hint">Sin daños detectados con este umbral.</p>'}
        <button class="btn ghost sm" id="m-zip">⬇ Descargar análisis</button>
        ${c.id ? '<button class="btn danger sm" id="m-del">Eliminar captura</button>' : '<p class="hint">Resultado no guardado.</p>'}
      </div></div>`;
  $("#modal").hidden = false;
  $("#modal-body").querySelectorAll(".tabs button").forEach((b) => b.onclick = () => {
    $("#modal-body").querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    $("#m-img").src = b.dataset.t === "a" ? c.url_anotada : c.url_imagen;
  });
  $("#m-zip").onclick = (e) => descargarCaptura(c, e.currentTarget);
  if (c.id) $("#m-del").onclick = async () => {
    if (!confirm("¿Eliminar esta captura y sus archivos? No se puede deshacer.")) return;
    try { await api("/api/capturas/" + c.id, { method: "DELETE" }); closeModal(); toast("Captura eliminada.", "ok"); current = null; route(); }
    catch (e) { toast(e.message, "err"); }
  };
}
window.openCaptura = openCaptura;

async function openVideo(id) {
  let res;
  try { res = await api("/api/videos/" + id); } catch (e) { return toast(e.message, "err"); }
  $("#modal-body").innerHTML = '<div id="vm"></div><button class="btn danger sm" id="vm-del">Eliminar video del seguimiento</button>';
  $("#modal").hidden = false;
  renderVideo($("#vm"), res);
  $("#vm-del").onclick = async () => {
    if (!confirm("¿Eliminar este análisis de video y sus imágenes? No se puede deshacer.")) return;
    try { await api("/api/videos/" + id, { method: "DELETE" }); closeModal(); toast("Video eliminado.", "ok"); current = null; route(); }
    catch (e) { toast(e.message, "err"); }
  };
}

/* ---------------- seguimiento ---------------- */
let chSeg, segTramo = null;
async function loadSeguimiento() {
  const sel = $("#s-tramo");
  let ts;
  try { ts = await cargarSelectTramos(sel, segTramo); } catch (e) { return toast(e.message, "err"); }
  if (!ts.length) { $("#s-body").innerHTML = '<div class="card empty">Primero <a href="#tramos">crea un tramo</a> y analiza fotos.</div>'; $("#s-info").textContent = ""; return; }
  segTramo = sel.value;
  await renderSeguimiento(sel.value);
}
$("#s-tramo").onchange = (e) => { segTramo = e.target.value; renderSeguimiento(segTramo); };

function regresion(puntos) {
  const xs = puntos.map((p) => dayNum(p.fecha)), ys = puntos.map((p) => p.indice), n = xs.length;
  const mx = xs.reduce((a, b) => a + b) / n, my = ys.reduce((a, b) => a + b) / n;
  const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0);
  if (!sxx) return null;
  const m = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0) / sxx;
  return { m, b: my - m * mx, x0: xs[0], x1: xs[n - 1] };
}

async function renderSeguimiento(id) {
  const body = $("#s-body");
  let s;
  try { s = await api(`/api/tramos/${id}/seguimiento`); } catch (e) { return toast(e.message, "err"); }
  const caps = s.capturas, t = s.tramo;
  $("#s-info").textContent = t.descripcion || "";
  const vids = s.videos || [];
  const tablaVideos = () => `<div class="card"><h2>Videos analizados</h2><table><thead><tr><th>Fecha de inicio</th><th>Archivo</th><th>Índice medio</th><th>Máximo</th><th>Con daños</th><th>Calificación</th><th>Sensib.</th></tr></thead><tbody>` +
    vids.map((v) => `<tr class="click" data-vid="${v.id}"><td>${esc(fmtDT(v.fecha_inicio))}</td><td>${esc(v.archivo)}</td><td><b>${v.indice_medio.toFixed(1)}</b></td><td>${v.indice_max.toFixed(1)}</td><td>${v.pct_afectados.toFixed(0)}%</td><td>${badge(v.calificacion)}</td><td>${esc(v.perfil)}</td></tr>`).join("") + "</tbody></table></div>";
  if (!caps.length) {
    chSeg?.destroy(); chSeg = null;
    body.innerHTML = vids.length ? tablaVideos() + '<p class="hint">Aún no hay fotos en este tramo: la gráfica de evolución aparece cuando haya fotos con fechas distintas.</p>'
      : '<div class="card empty">Este tramo aún no tiene capturas. <a href="#analizar">Analiza la primera foto o video</a>.</div>';
    return;
  }
  const first = s.puntos[0], last = s.puntos[s.puntos.length - 1];
  const delta = last.indice - first.indice;
  const tr = s.tendencia;
  const optsCaps = (sel) => caps.map((c, i) => `<option value="${c.id}" ${i === sel ? "selected" : ""}>${esc(fmtDT(c.fecha_captura))} · índice ${c.indice_severidad.toFixed(1)}</option>`).join("");

  body.innerHTML = `
    <div class="kpis">
      <div class="kpi"><span>Fotos</span><b>${caps.length}</b><em>en ${s.puntos.length} fecha(s)</em></div>
      <div class="kpi"><span>Último índice</span><b>${last.indice.toFixed(1)}</b><em>${esc(fmtDay(last.fecha))}</em></div>
      <div class="kpi"><span>Cambio total</span><b>${s.puntos.length > 1 ? (delta > 0 ? "+" : "") + delta.toFixed(1) : "—"}</b><em>${s.puntos.length > 1 ? "desde " + esc(fmtDay(first.fecha)) : "se necesita otra fecha"}</em></div>
      <div class="kpi"><span>Estado actual</span><b style="font-size:22px;padding-top:6px">${badge(caps[caps.length - 1].calificacion)}</b><em>última captura</em></div>
    </div>
    <div class="card">
      <h2>Evolución del índice de severidad</h2>
      ${s.perfiles.length > 1 ? '<p class="warn">Las fotos de este tramo se analizaron con sensibilidades distintas (normal y sensible). Sus índices no son directamente comparables: la tendencia puede estar sesgada.</p>' : ""}
      <div class="trend"><span class="tag t-${tr.disponible ? tr.sentido : "incierta"}">${tr.disponible ? (tr.sentido === "incierta" ? "sin tendencia clara" : esc(tr.sentido)) : "sin tendencia"}</span><span>${esc(tr.mensaje)}</span></div>
      <div class="chart-box" style="height:300px;margin-top:12px"><canvas id="ch-seg"></canvas></div>
      <p class="hint">El índice es una heurística del proyecto (no un estándar como PCI/IRI) y solo es comparable entre fotos tomadas desde un encuadre similar. La tendencia es una recta ajustada a pocos puntos: úsala como indicio, no como predicción.</p>
    </div>
    <div class="card">
      <h2>Comparar dos capturas</h2>
      <div class="cmp">
        <figure><select id="cmp-a">${optsCaps(0)}</select><img id="cmp-ai" alt=""><figcaption id="cmp-ac"></figcaption></figure>
        <figure><select id="cmp-b">${optsCaps(caps.length - 1)}</select><img id="cmp-bi" alt=""><figcaption id="cmp-bc"></figcaption></figure>
      </div>
    </div>
    <div class="card">
      <h2>Línea de tiempo</h2>
      <div class="timeline">${caps.map((c) => `<div class="tl" data-cap="${c.id}"><img loading="lazy" src="${esc(c.url_anotada)}" alt=""><div><b>${esc(fmtDT(c.fecha_captura))}</b><span>${badge(c.calificacion)} <b>${c.indice_severidad.toFixed(1)}</b></span></div></div>`).join("")}</div>
    </div>${vids.length ? tablaVideos() : ""}`;

  // gráfico
  const pts = s.puntos.map((p) => ({ x: dayNum(p.fecha), y: p.indice }));
  const vpts = vids.map((v) => ({ x: dayNum(v.fecha), y: v.indice_medio }));
  const xs = [...pts, ...vpts].map((p) => p.x);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const datasets = [{ label: "Índice", data: pts, borderColor: "#0f172a", backgroundColor: "#0f172a", pointRadius: 5, pointHoverRadius: 7, tension: 0, borderWidth: 2.5 }];
  const rg = s.puntos.length >= 3 ? regresion(s.puntos) : null;
  if (rg) datasets.push({ label: "Tendencia", data: [{ x: rg.x0, y: Math.max(0, Math.min(100, rg.m * rg.x0 + rg.b)) }, { x: rg.x1, y: Math.max(0, Math.min(100, rg.m * rg.x1 + rg.b)) }], borderColor: "#b45309", borderDash: [6, 5], pointRadius: 0, borderWidth: 2 });
  if (vpts.length) datasets.push({ label: "Video (índice medio)", data: vpts, showLine: false, pointStyle: "triangle", pointRadius: 8, pointHoverRadius: 10, borderColor: "#7c3aed", backgroundColor: "#7c3aed" });
  chSeg?.destroy();
  const spanD = xmax - xmin;
  const pad = xmax === xmin ? 3 : Math.max(1, Math.round(spanD * 0.04));
  chSeg = new Chart($("#ch-seg"), {
    type: "line", data: { datasets }, plugins: [bandsPlugin],
    options: {
      maintainAspectRatio: false, parsing: false,
      scales: {
        x: { type: "linear", min: xmin - pad, max: xmax + pad, ticks: { maxTicksLimit: 8, callback: (v) => new Date(v * 86400000).toLocaleDateString("es-EC", { timeZone: "UTC", day: "2-digit", month: "short" }) }, grid: { display: false } },
        y: { min: 0, max: 100, title: { display: true, text: "Índice de severidad" } },
      },
      plugins: { legend: { display: !!rg || vpts.length > 0, labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { callbacks: { title: (it) => fmtDay(new Date(it[0].parsed.x * 86400000).toISOString().slice(0, 10)), label: (it) => `${it.dataset.label}: ${it.parsed.y.toFixed(1)}` } } },
    },
  });

  // comparación
  const byId = Object.fromEntries(caps.map((c) => [c.id, c]));
  const paint = (selId, imgId, capId) => {
    const c = byId[$(selId).value];
    $(imgId).src = c.url_anotada;
    $(imgId).onclick = () => openCaptura(c.id);
    $(capId).innerHTML = `${badge(c.calificacion)} índice <b>${c.indice_severidad.toFixed(1)}</b> · ${c.n_detecciones} daño(s)`;
  };
  const both = () => { paint("#cmp-a", "#cmp-ai", "#cmp-ac"); paint("#cmp-b", "#cmp-bi", "#cmp-bc"); };
  $("#cmp-a").onchange = $("#cmp-b").onchange = both;
  both();
}

/* ---------------- tramos ---------------- */
async function loadTramos() {
  let ts;
  try { ts = await api("/api/tramos"); } catch (e) { return toast(e.message, "err"); }
  $("#tr-list").innerHTML = ts.length ? `<table><thead><tr><th>Tramo</th><th>Contenido</th><th>Último estado</th><th></th></tr></thead><tbody>` +
    ts.map((t) => `<tr><td><b>${esc(t.nombre)}</b><br><small>${esc([t.ciudad, t.descripcion].filter(Boolean).join(" · "))}</small></td>
      <td>${t.n_capturas} foto(s)<br><small>${t.n_videos} video(s)</small></td>
      <td>${t.ultima_calificacion ? badge(t.ultima_calificacion) + " <small>" + t.ultimo_indice.toFixed(1) + " · " + esc(fmtDT(t.ultima_fecha)) + "</small>" : '<small>sin fotos</small>'}</td>
      <td style="white-space:nowrap"><button class="btn ghost sm" data-seg="${t.id}">Seguimiento</button> <button class="btn danger sm" data-del="${t.id}" data-n="${esc(t.nombre)}">Eliminar</button></td></tr>`).join("") + "</tbody></table>"
    : '<div class="empty">Aún no hay tramos.</div>';
}
$("#tr-list").addEventListener("click", async (e) => {
  const s = e.target.closest("[data-seg]");
  if (s) { segTramo = s.dataset.seg; location.hash = "#seguimiento"; return; }
  const d = e.target.closest("[data-del]");
  if (d && confirm(`¿Eliminar el tramo “${d.dataset.n}” con TODAS sus fotos y detecciones? No se puede deshacer.`)) {
    try { await api("/api/tramos/" + d.dataset.del, { method: "DELETE" }); toast("Tramo eliminado.", "ok"); loadTramos(); }
    catch (err) { toast(err.message, "err"); }
  }
});
$("#form-tr").onsubmit = async (e) => {
  e.preventDefault();
  const num = (id) => ($(id).value.trim() === "" ? null : Number($(id).value));
  const body = { nombre: $("#t-nombre").value.trim(), ciudad: $("#t-ciudad").value.trim() || null, descripcion: $("#t-desc").value.trim() || null, lat: num("#t-lat"), lon: num("#t-lon") };
  try { await api("/api/tramos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); e.target.reset(); toast("Tramo creado.", "ok"); loadTramos(); }
  catch (err) { toast(err.message, "err"); }
};

/* ---------------- arranque ---------------- */
fetch("/api/health").then(() => { $("#maxmb").textContent = "15"; }).catch(() => {});
refreshStatus(); setInterval(refreshStatus, 30000);
route();
