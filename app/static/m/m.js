"use strict";
/* Vialidad móvil: una sola pantalla. Todo el análisis ocurre en el servidor (PC). */
const CLASES = {
  pothole: { n: "Bache / daño mayor", c: "#dc2626" },
  alligator_crack: { n: "Piel de cocodrilo", c: "#ea580c" },
  transverse_crack: { n: "Grieta transversal", c: "#2563eb" },
  longitudinal_crack: { n: "Grieta longitudinal", c: "#0d9488" },
};
const CAL_COLOR = { Bueno: "#16a34a", Regular: "#ca8a04", Malo: "#ea580c", "Muy malo": "#dc2626" };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nom = (k) => (CLASES[k] ? CLASES[k].n : k);
const fmtT = (s) => { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const enApp = typeof window.Android !== "undefined";

let archivo = null, esVideo = false, urlPrevia = null;
let abortar = null, jobId = null, cancelado = false;
let R = null; // resultado actual {tipo, ...}
let chart = null, chartH = null;
let desdeHist = false, vistaActual = "principal";
let CFG = { video_max_frames: 300, video_max_frames_cap: 6000, ms_por_imagen: 94 };

function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), err ? 6000 : 3500);
}
function aviso(msg, info) {
  const a = $("#aviso"); if (!msg) { a.hidden = true; return; }
  a.textContent = msg; a.className = "aviso" + (info ? " info" : ""); a.hidden = false;
}

/* ---------- conexión ---------- */
async function estado() {
  try {
    const r = await fetch("/api/health", { cache: "no-store" });
    if (r.status === 401) { $("#estado").textContent = "Acceso no autorizado"; aviso("El servidor pide una clave de acceso. Abre desde la app la dirección con la clave (…/acceso?t=CLAVE)."); return; }
    $("#estado").textContent = "Conectado al servidor";
  } catch {
    $("#estado").textContent = "Sin conexión";
    aviso("No se puede llegar al servidor. Revisa que el PC esté encendido, con el servidor corriendo y en la misma red wifi.");
  }
}

/* ---------- selección ---------- */
function elegir(file) {
  if (!file) return;
  limpiarResultado();
  fechaFija = null; $("#o-fecha").removeAttribute("step");
  archivo = file; esVideo = file.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|3gp|mkv)$/i.test(file.name);
  if (urlPrevia) URL.revokeObjectURL(urlPrevia);
  urlPrevia = URL.createObjectURL(file);
  const mb = (file.size / 1048576).toFixed(1);
  $("#previa").innerHTML = (esVideo ? `<video src="${urlPrevia}#t=0.1" muted playsinline preload="metadata"></video>` : `<img src="${urlPrevia}" alt="">`) +
    `<div><b>${esc(file.name || (esVideo ? "video" : "foto"))}</b><small>${esVideo ? "Video" : "Foto"} · ${mb} MB</small></div>`;
  $("#previa").hidden = false; $("#opciones").hidden = false; $("#o-video").hidden = !esVideo;
  duracionVideo = 0;
  if (esVideo) { const v = document.querySelector("#previa video"); if (v) v.addEventListener("loadedmetadata", () => { duracionVideo = v.duration || 0; if (radio("fch") === "manual") sugerirFecha(); }); }
  $("#o-gpx").value = "";
  if (radio("fch") === "manual") sugerirFecha();
  actualizarHints(); actualizarGuardar();
}
["#in-foto", "#in-video", "#in-gal"].forEach((s) => $(s).addEventListener("change", (e) => { elegir(e.target.files[0]); e.target.value = ""; }));

function dest() { return document.querySelector("input[name=dest]:checked").value; }
function lsGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch {} }

async function cargarTramos(seleccionar) {
  const sel = $("#o-tramo");
  try {
    const r = await fetch("/api/tramos", { cache: "no-store" });
    const ts = await leer(r);
    sel.innerHTML = ts.length ? ts.map((t) => `<option value="${t.id}" data-nombre="${esc(t.nombre)}">${esc(t.nombre)}${t.ciudad ? " · " + esc(t.ciudad) : ""}</option>`).join("") : '<option value="">(no hay tramos: crea uno)</option>';
    const quiero = String(seleccionar || lsGet("tramo") || "");
    if (quiero && ts.some((t) => String(t.id) === quiero)) sel.value = quiero;
    if (!ts.length) $("#f-nuevo").hidden = false;
  } catch (e) {
    sel.innerHTML = '<option value="">(no se pudieron cargar los tramos)</option>';
  }
}
function actualizarDest() {
  const g = dest() === "guardar";
  $("#o-guardar").hidden = !g;
  if (g) actualizarGuardar();
  $("#dest-hint").textContent = g
    ? "El resultado, las imágenes y el conteo quedan guardados en la base de datos del servidor, dentro del tramo elegido."
    : "El resultado solo se muestra aquí; no se guarda nada en el servidor.";
  if (g && !$("#o-tramo").options.length) cargarTramos();
}
document.querySelectorAll("input[name=dest]").forEach((r) => r.addEventListener("change", actualizarDest));
function tramoElegido() {
  const v = $("#o-tramo").value;
  return v ? { id: v, nombre: $("#o-tramo").selectedOptions[0].dataset.nombre || $("#o-tramo").selectedOptions[0].textContent } : null;
}

/* ---------- límite de fotogramas ---------- */
const OPC_FRAMES = [250, 500, 1000, 2000, 4000, 6000];
async function cargarConfig() {
  try { const c = await leer(await fetch("/api/config", { cache: "no-store" })); CFG = { ...CFG, ...c }; } catch {}
  const cap = CFG.video_max_frames_cap || 6000;
  let ops = OPC_FRAMES.filter((n) => n <= cap);
  if (!ops.includes(cap) && cap < 6000) ops.push(cap);
  const sel = $("#o-maxfr");
  const pref = Number(lsGet("maxfr")) || 500;
  sel.innerHTML = ops.map((n) => `<option value="${n}">${n.toLocaleString("es-EC")}</option>`).join("");
  sel.value = ops.includes(pref) ? String(pref) : String(ops.includes(500) ? 500 : ops[0]);
  actualizarMaxfr();
}
function actualizarMaxfr() {
  const n = Number($("#o-maxfr").value) || 0, ms = CFG.ms_por_imagen || 94;
  const seg = (n * ms) / 1000;
  const t = seg < 90 ? Math.round(seg) + " s" : Math.round(seg / 60) + " min";
  $("#maxfr-hint").textContent = `Si el video tiene más fotogramas, se analiza uno de cada varios para no pasar de ${n.toLocaleString("es-EC")}. Tiempo máximo estimado ≈ ${t} (solo inferencia, ${Math.round(ms)} ms por fotograma en este PC).`;
}
$("#o-maxfr").addEventListener("change", () => { lsSet("maxfr", $("#o-maxfr").value); actualizarMaxfr(); });

/* ---------- fecha, ubicación, GPX ---------- */
function radio(n) { return document.querySelector(`input[name=${n}]:checked`).value; }
const pad = (n) => String(n).padStart(2, "0");
function aLocalISO(dt) { return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`; }
let duracionVideo = 0;

let fechaFija = null;   // hora exacta (con segundos) de inicio de un recorrido grabado en la app
function sugerirFecha() {
  if (fechaFija) { $("#o-fecha").value = fechaFija; return; }
  let t = archivo && archivo.lastModified ? archivo.lastModified : Date.now();
  if (esVideo && duracionVideo) t -= duracionVideo * 1000;   // el archivo se modifica al terminar de grabar
  $("#o-fecha").value = aLocalISO(new Date(t));
}
/* ---------- recorrido con GPS (solo dentro de la app Android) ---------- */
const aLocalISOs = (dt) => `${aLocalISO(dt)}:${pad(dt.getSeconds())}`;
if (window.Android && typeof Android.grabarRecorrido === "function") {
  $("#btn-recorrido").hidden = false; $("#recorrido-hint").hidden = false;
  $("#btn-recorrido").onclick = () => { try { Android.grabarRecorrido(); } catch (e) { toast("No se pudo abrir la cámara", true); } };
}
window.onRecorrido = async (r) => {
  if (!r || !r.ok) { toast(r && r.error ? r.error : (r && r.cancelado ? "Grabación cancelada" : "No se pudo grabar el recorrido"), !(r && r.cancelado)); return; }
  try {
    toast("Cargando la grabación…");
    const vb = await (await fetch(r.video)).blob();
    const video = new File([vb], "recorrido.mp4", { type: "video/mp4", lastModified: r.inicio_ms + Math.round(r.dur_s * 1000) });
    elegir(video);
    fechaFija = aLocalISOs(new Date(r.inicio_ms));
    document.querySelector("input[name=fch][value=manual]").checked = true;
    $("#o-fecha").step = 1; $("#o-fecha").value = fechaFija; $("#o-desfase").value = 0;
    if (r.gpx) {
      const gb = await (await fetch(r.gpx)).blob();
      const dt = new DataTransfer(); dt.items.add(new File([gb], "recorrido.gpx", { type: "application/gpx+xml" }));
      $("#o-gpx").files = dt.files;
      toast(`Recorrido listo: ${Math.round(r.dur_s)} s, ${r.puntos} puntos GPS`);
    } else {
      toast("Grabado sin ruta GPS (no hubo señal): los daños no tendrán ubicación", true);
    }
    actualizarGuardar();
    $("#opciones").scrollIntoView({ behavior: "smooth" });
  } catch (e) { toast("No se pudo cargar la grabación: " + (e.message || e), true); }
};

function actualizarGuardar() {
  const man = radio("fch") === "manual";
  $("#l-fecha").hidden = !man;
  $("#t-fecha").textContent = esVideo ? "Fecha y hora en que EMPEZÓ el video" : "Fecha y hora de la foto";
  $("#fch-hint").textContent = man
    ? (fechaFija ? "Hora exacta en que empezó tu grabación (no la cambies si usas la ruta GPS)." : "Sugerida a partir del archivo; corrígela si no es la correcta.")
    : (esVideo ? "Automática: se usa la hora en que se envía el análisis." : "Automática: se usa la fecha de la foto (EXIF) o, si no la trae, la hora actual.");
  $("#g-ubi").hidden = esVideo;
  $("#g-gpx").hidden = !esVideo;
  $("#l-ubi").hidden = radio("ubi") !== "manual";
  const hayGpx = esVideo && $("#o-gpx").files && $("#o-gpx").files.length > 0;
  $("#l-desfase").hidden = !hayGpx;
  $("#gpx-hint").textContent = hayGpx ? "Con GPX hay que indicar la hora de inicio del video (se cambió a «Elegir»). Debe coincidir con el reloj del GPX." : "";
}
document.querySelectorAll("input[name=fch],input[name=ubi]").forEach((r) => r.addEventListener("change", () => { if (radio("fch") === "manual" && !$("#o-fecha").value) sugerirFecha(); actualizarGuardar(); }));
$("#o-gpx").addEventListener("change", () => {
  if ($("#o-gpx").files.length && radio("fch") !== "manual") { document.querySelector("input[name=fch][value=manual]").checked = true; sugerirFecha(); }
  actualizarGuardar();
});

/* ubicación actual: en la app usa el GPS del teléfono; en un navegador solo funciona con HTTPS */
let cbUbicacion = null;
window.onUbicacion = (lat, lon, err) => { const cb = cbUbicacion; cbUbicacion = null; if (cb) cb(lat, lon, err); };
function ubicacionActual(cb) {
  cbUbicacion = cb;
  if (enApp && window.Android.getLocation) { toast("Buscando ubicación…"); window.Android.getLocation(); return; }
  if (!navigator.geolocation || !window.isSecureContext) { cbUbicacion = null; cb(null, null, "Este navegador solo da la ubicación con HTTPS. Usa la app o escribe las coordenadas."); return; }
  navigator.geolocation.getCurrentPosition((p) => { cbUbicacion = null; cb(p.coords.latitude, p.coords.longitude, null); }, (e) => { cbUbicacion = null; cb(null, null, "No se pudo obtener la ubicación (" + e.message + ")"); }, { enableHighAccuracy: true, timeout: 20000 });
}
function conUbicacion(latSel, lonSel) {
  ubicacionActual((lat, lon, err) => {
    if (err || lat == null) { toast(err || "Sin ubicación", true); return; }
    $(latSel).value = Number(lat).toFixed(6); $(lonSel).value = Number(lon).toFixed(6); toast("Ubicación cargada");
  });
}
$("#btn-ubi").onclick = () => conUbicacion("#o-lat", "#o-lon");
$("#btn-ubi-tramo").onclick = () => conUbicacion("#n-lat", "#n-lon");

function leerCoord(txt, min, max, nombre) {
  const t = String(txt || "").trim().replace(",", ".");
  if (t === "") return null;
  const v = Number(t);
  if (!isFinite(v) || v < min || v > max) throw new Error(`${nombre} no válida (entre ${min} y ${max})`);
  return v;
}

/* ---------- ajustes: tramos ---------- */
function ir(v) {
  if (v === "principal" && desdeHist) { limpiarResultado(); desdeHist = false; }
  vistaActual = v;
  $("#v-captura").hidden = v !== "principal";
  $("#v-ajustes").hidden = v !== "ajustes";
  $("#v-historial").hidden = v !== "historial";
  $("#v-resultado").hidden = !(R && ((v === "principal" && !desdeHist) || v === "detalle"));
  if (v === "ajustes") { $("#a-app").hidden = !enApp; $("#a-srv").textContent = "Servidor actual: " + location.origin; cargarListaTramos(); }
  if (v === "historial") cargarHistorial();
  window.scrollTo(0, 0);
}
function navegar(v) {
  if (!$("#v-progreso").hidden) { toast("Espera a que termine el análisis"); return; }
  ir(vistaActual === v ? "principal" : v);
}
$("#btn-ajustes").onclick = () => navegar("ajustes");
$("#btn-hist").onclick = () => navegar("historial");
$("#h-cerrar").onclick = () => ir("principal");
$("#btn-volver").onclick = () => { ir("principal"); cargarTramos(); };
$("#btn-nuevo-tramo").onclick = () => ir("ajustes");
$("#btn-srv").onclick = () => { if (enApp) window.Android.changeServer(); };
async function cargarListaTramos() {
  const box = $("#lista-tramos");
  try {
    const ts = await leer(await fetch("/api/tramos", { cache: "no-store" }));
    box.innerHTML = ts.length ? ts.map((t) => `<div class="tr"><span><b>${esc(t.nombre)}</b>${t.ciudad ? "<br><small>" + esc(t.ciudad) + "</small>" : ""}</span><small>${t.n_capturas} ${t.n_capturas === 1 ? "foto" : "fotos"} · ${t.n_videos} ${t.n_videos === 1 ? "video" : "videos"}</small></div>`).join("") : "Todavía no hay tramos.";
  } catch (e) { box.textContent = "No se pudo cargar la lista: " + (e.message || e); }
}
$("#btn-crear-tramo").onclick = async () => {
  const nombre = $("#n-nombre").value.trim();
  if (nombre.length < 2) { toast("Escribe el nombre del tramo (mínimo 2 letras)", true); return; }
  let lat, lon;
  try { lat = leerCoord($("#n-lat").value, -90, 90, "Latitud"); lon = leerCoord($("#n-lon").value, -180, 180, "Longitud"); if ((lat == null) !== (lon == null)) throw new Error("Indica latitud y longitud juntas"); }
  catch (e) { toast(e.message, true); return; }
  try {
    const r = await fetch("/api/tramos", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, ciudad: $("#n-ciudad").value.trim() || null, descripcion: $("#n-desc").value.trim() || null, lat, lon }) });
    const t = await leer(r);
    ["#n-nombre", "#n-ciudad", "#n-desc", "#n-lat", "#n-lon"].forEach((s) => ($(s).value = ""));
    lsSet("tramo", t.id); await cargarTramos(t.id); await cargarListaTramos(); toast("Tramo creado: " + t.nombre);
  } catch (e) { toast("No se pudo crear: " + (e.message || e), true); }
};

function modo() { return document.querySelector("input[name=modo]:checked").value; }
function actualizarHints() {
  const m = modo();
  $("#l-calidad").hidden = m !== "anotado"; $("#l-intervalo").hidden = m !== "fotogramas";
  $("#modo-hint").textContent = m === "anotado"
    ? "Devuelve el mismo video con los daños marcados en recuadros, más un conteo de daños distintos."
    : "Analiza un fotograma cada cierto tiempo y muestra los más dañados, sin generar video.";
  const dur = 0; // la duración no se conoce hasta subir; se estima con el límite del servidor
  $("#eta-hint").textContent = "El análisis se hace en el PC: aproximadamente 10 fotogramas por segundo. Un video de 1 minuto puede tardar unos minutos.";
}
document.querySelectorAll("input[name=modo]").forEach((r) => r.addEventListener("change", actualizarHints));

/* ---------- análisis ---------- */
function vista(v) { $("#v-captura").hidden = v !== "c"; $("#v-progreso").hidden = v !== "p"; }
function limpiarResultado() { $("#v-resultado").hidden = true; $("#v-resultado").innerHTML = ""; R = null; if (chart) { chart.destroy(); chart = null; } }

function progreso(pct, msg, titulo) {
  const pb = $("#pb");
  if (pct == null) { pb.classList.add("ind"); } else { pb.classList.remove("ind"); $("#pb-i").style.width = pct + "%"; }
  if (msg) $("#prog-msg").textContent = msg;
  if (titulo) $("#prog-titulo").textContent = titulo;
}

$("#btn-analizar").onclick = async () => {
  if (!archivo) return;
  aviso(""); desdeHist = false; limpiarResultado(); cancelado = false; jobId = null;
  vista("p"); progreso(null, "Subiendo al servidor…", esVideo ? "Analizando video…" : "Analizando foto…");
  window.scrollTo(0, 0);
  const guardar = dest() === "guardar";
  const tr = guardar ? tramoElegido() : null;
  if (guardar && !tr) { vista("c"); aviso("Elige o crea un tramo para guardar en el servidor."); return; }
  if (tr) lsSet("tramo", tr.id);
  const fd = new FormData();
  fd.append("file", archivo, archivo.name || (esVideo ? "video.mp4" : "foto.jpg"));
  fd.append("sensibilidad", $("#o-sens").value);
  if (guardar) {
    fd.append("tramo_id", tr.id);
    const n = $("#o-notas").value.trim(); if (n) fd.append("notas", n);
    try {
      if (radio("fch") === "manual") {
        if (!$("#o-fecha").value) throw new Error("Elige la fecha y hora");
        fd.append(esVideo ? "fecha_inicio" : "fecha_captura", $("#o-fecha").value);
      }
      if (!esVideo && radio("ubi") === "manual") {
        const la = leerCoord($("#o-lat").value, -90, 90, "Latitud"), lo = leerCoord($("#o-lon").value, -180, 180, "Longitud");
        if (la == null || lo == null) throw new Error("Indica latitud y longitud");
        fd.append("lat", la); fd.append("lon", lo);
      }
      if (esVideo && $("#o-gpx").files.length) {
        fd.append("gpx", $("#o-gpx").files[0]); fd.append("desfase_s", String(Number($("#o-desfase").value) || 0));
      }
    } catch (e) { vista("c"); aviso(e.message || String(e)); return; }
  }
  abortar = new AbortController();
  try {
    if (!esVideo) {
      const r = await fetch(guardar ? "/api/capturas" : "/api/analizar", { method: "POST", body: fd, signal: abortar.signal });
      const j = await leer(r);
      mostrarFoto(guardar ? capturaAFoto(j, tr) : j);
    } else {
      fd.append("modo", modo()); fd.append("guardar", guardar ? "true" : "false");
      fd.append("cada_n", $("#o-cada").value); fd.append("intervalo_s", $("#o-int").value); fd.append("max_frames", $("#o-maxfr").value);
      const r = await fetch("/api/videos", { method: "POST", body: fd, signal: abortar.signal });
      const { job_id } = await leer(r);
      jobId = job_id;
      const res = await esperar(job_id);
      await mostrarVideo(res, tr);
    }
    vista("c");
  } catch (e) {
    vista("c");
    if (!cancelado) aviso("No se pudo analizar: " + (e.message || e));
  } finally { abortar = null; jobId = null; }
};

async function leer(r) {
  let j = null; try { j = await r.json(); } catch {}
  if (!r.ok) throw new Error((j && (j.detail?.message || (typeof j.detail === "string" ? j.detail : null) || j.error)) || "Error " + r.status);
  return j;
}

async function esperar(id) {
  for (;;) {
    if (cancelado) throw new Error("cancelado");
    const r = await fetch("/api/videos/jobs/" + id, { cache: "no-store" });
    const j = await leer(r);
    if (j.estado === "listo") return j.resultado;
    if (j.estado === "error") throw new Error(j.error || "Error en el análisis");
    if (j.estado === "cancelado") throw new Error("cancelado");
    if (j.total) {
      const pct = Math.min(99, Math.round((100 * j.hechos) / j.total));
      const faltan = j.hechos > 3 && j.transcurrido_s ? Math.round((j.transcurrido_s * (j.total - j.hechos)) / j.hechos) : null;
      progreso(pct, `${j.hechos} de ${j.total} fotogramas (${pct} %)` + (faltan != null ? ` · faltan ≈ ${fmtT(faltan)}` : ""));
    } else progreso(null, "Preparando…");
    await new Promise((s) => setTimeout(s, 900));
  }
}

$("#btn-cancelar").onclick = async () => {
  cancelado = true;
  if (abortar) abortar.abort();
  if (jobId) { try { await fetch("/api/videos/jobs/" + jobId, { method: "DELETE" }); } catch {} }
  vista("c"); toast("Análisis cancelado");
};

/* ---------- resultados ---------- */
function chips(conteo) {
  const e = Object.entries(conteo || {}).filter(([, n]) => n > 0);
  if (!e.length) return '<p class="hint">No se detectaron daños.</p>';
  return '<div class="chips">' + e.map(([k, n]) => `<span class="chip"><i style="background:${(CLASES[k] || {}).c || "#64748b"}"></i>${esc(nom(k))}: <b>${n}</b></span>`).join("") + "</div>";
}
const badge = (c) => `<span class="badge b-${c === "Muy malo" ? "Muy" : esc(c)}">${esc(c)}</span>`;
const NOTA = '<div class="nota">El índice de severidad es una medida propia (heurística) basada en el área de los daños detectados; no equivale a PCI ni IRI. El modelo puede dar falsas alarmas y omitir daños: revise visualmente.</div>';

function capturaAFoto(c, tr) {
  return { guardado: true, id: c.id, archivo: c.archivo_original, fecha: c.fecha_captura, tramo: c.tramo_nombre || (tr && tr.nombre), imagen_anotada: c.url_anotada,
    indice_severidad: c.indice_severidad, calificacion: c.calificacion, n_detecciones: c.n_detecciones,
    conteo: c.conteo || {}, detecciones: c.detecciones || [], tiempo_inferencia_ms: c.tiempo_inferencia_ms,
    perfil: c.perfil, conf_umbral: c.conf_umbral, modelo_version: c.modelo_version,
    gps_exif: c.lat != null ? { lat: c.lat, lon: c.lon } : null };
}

function mostrarFoto(j) {
  R = { tipo: "foto", j };
  const cal = j.calificacion;
  $("#v-resultado").innerHTML = `
  <div class="card">
    ${desdeHist ? '<button class="btn ghost small" id="btn-hv">← Volver a los seguimientos</button>' : ""}
    <h2>Resultado</h2>
    <img class="resimg" id="img-res" src="${j.imagen_anotada}" alt="Foto con daños marcados">
    <div class="kpis">
      <div><span>Índice de severidad</span><b>${j.indice_severidad}</b></div>
      <div><span>Calificación</span>${badge(cal)}</div>
      <div><span>Daños detectados</span><b>${j.n_detecciones}</b></div>
      <div><span>Tiempo</span><b>${(j.tiempo_inferencia_ms / 1000).toFixed(1)} s</b></div>
    </div>
    ${chips(j.conteo)}
    ${j.guardado ? `<div class="ok">✔ Guardado en el servidor · tramo «${esc(j.tramo)}» · captura n.º ${j.id}</div>` : ""}
    ${NOTA}
    <button class="btn prim" id="btn-pdf">Guardar informe (PDF)</button>
    <button class="btn dark" id="btn-img">Guardar foto marcada</button>
  </div>`;
  $("#v-resultado").hidden = false;
  enlazarHist();
  $("#img-res").onclick = () => visor(j.imagen_anotada);
  $("#btn-pdf").onclick = () => informe();
  $("#btn-img").onclick = () => guardarDataUrl(j.imagen_anotada, nombreBase() + "_marcada.jpg");
  if (!desdeHist) $("#v-resultado").scrollIntoView({ behavior: "smooth" });
}

function conteoVivo() {
  const c = {};
  R.hall.forEach((h) => { if (!h.descartado) c[h.clase] = (c[h.clase] || 0) + 1; });
  return c;
}

async function mostrarVideo(res, tr) {
  const m = res.resumen;
  R = { tipo: "video", res, m, tramo: tr ? tr.nombre : null, hall: (res.hallazgos || []).map((h) => ({ ...h })) };
  let av = "";
  if (m.limite_aplicado) av += `<div class="warn">Para no tardar demasiado se analizó menos detalle del pedido (1 de cada ${m.cada_n || "…"} fotogramas / intervalo ${m.intervalo_s} s).</div>`;
  if (res.hallazgos_truncado) av += '<div class="warn">Había demasiados daños distintos: se muestran solo los primeros.</div>';
  const medio = res.video_url
    ? `<video class="resvid" src="${res.video_url}" controls playsinline preload="metadata"></video><p class="hint">Si el video no se reproduce aquí, use «Guardar video marcado» y ábralo con otro reproductor.</p>`
    : "";
  const mejores = (res.mejores || []).length
    ? `<h3>Fotogramas más dañados</h3><div class="tira">${res.mejores.map((x, i) => `<figure><img src="${x.imagen}" data-i="${i}" alt=""><figcaption>${fmtT(x.t)} · índice ${x.indice}</figcaption></figure>`).join("")}</div>` : "";
  $("#v-resultado").innerHTML = `
  <div class="card">
    ${desdeHist ? '<button class="btn ghost small" id="btn-hv">← Volver a los seguimientos</button>' : ""}
    <h2>Resultado ${m.modo === "anotado" ? "· video marcado" : "· por fotogramas"}</h2>
    ${av}${medio}
    <div class="kpis">
      <div><span>Índice medio</span><b>${m.indice_medio}</b></div>
      <div><span>Calificación</span>${badge(m.calificacion)}</div>
      <div><span>Índice máximo</span><b>${m.indice_max}</b></div>
      <div><span>Tramo afectado</span><b>${m.pct_afectados} %</b></div>
      <div><span>Duración</span><b>${fmtT(m.duracion_s)}</b></div>
      <div><span>Fotogramas analizados</span><b>${m.n_frames}</b></div>
    </div>
    ${res.guardado ? `<div class="ok">✔ Guardado en el servidor · tramo «${esc(R.tramo || "")}» · video n.º ${res.video_id}</div>` : ""}
    <h3>Conteo estimado de daños distintos: <span id="tot">0</span></h3>
    <div id="cont"></div>
    <p class="hint">Una misma grieta o bache puede contarse más de una vez, o dos daños distintos juntarse. Toque ✕ en una foto para descartar una falsa alarma y el conteo baja${res.guardado ? " (el descarte también se guarda en el servidor)" : ""}.</p>
    <div id="hall"></div>
    ${mejores}
    <h3>Evolución del índice</h3><div class="chartbox"><canvas id="ch"></canvas></div>
    ${NOTA}
    <button class="btn prim" id="btn-pdf">Guardar informe (PDF)</button>
    ${res.video_url ? '<button class="btn dark" id="btn-vid">Guardar video marcado</button>' : ""}
  </div>`;
  $("#v-resultado").hidden = false;
  enlazarHist();
  pintarHall();
  $("#btn-pdf").onclick = () => informe();
  const bv = $("#btn-vid"); if (bv) bv.onclick = () => descargarUrl(res.video_url, nombreBase() + "_marcado.mp4");
  document.querySelectorAll(".tira img").forEach((im) => (im.onclick = () => visor(im.src)));
  try {
    chart = new Chart($("#ch"), { type: "line", data: { labels: res.serie.map((s) => fmtT(s.t)), datasets: [{ data: res.serie.map((s) => s.indice), borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,.15)", fill: true, pointRadius: 0, tension: .25 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100 }, x: { ticks: { maxTicksLimit: 6 } } } } });
  } catch {}
  if (!desdeHist) $("#v-resultado").scrollIntoView({ behavior: "smooth" });
}

function pintarHall() {
  const c = conteoVivo(); const tot = Object.values(c).reduce((a, b) => a + b, 0);
  $("#tot").textContent = tot; $("#cont").innerHTML = chips(c);
  const h = R.hall;
  $("#hall").innerHTML = h.length
    ? `<details><summary><b>Dónde están los daños (${h.length})</b></summary><div class="hgrid" style="margin-top:10px">` +
      h.map((x, i) => `<div class="hc ${x.descartado ? "off" : ""}"><img src="${x.imagen}" loading="lazy" data-i="${i}" alt=""><button class="hx" data-i="${i}" aria-label="${x.descartado ? "Restaurar" : "Descartar"}">${x.descartado ? "↺" : "✕"}</button><div><b>${esc(nom(x.clase))}</b><br><small>${fmtT(x.t_ini)}${x.t_fin > x.t_ini ? "–" + fmtT(x.t_fin) : ""} · conf. ${Math.round(x.conf_max * 100)} %</small></div></div>`).join("") +
      "</div></details>"
    : '<p class="hint">No se detectaron daños distintos.</p>';
  document.querySelectorAll(".hx").forEach((b) => (b.onclick = async () => { const x = R.hall[+b.dataset.i]; const nuevo = !x.descartado;
    if (R.res.guardado) {
      try {
        const r = await fetch(`/api/videos/${R.res.video_id}/hallazgos/${x.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ descartado: nuevo }) });
        if (!r.ok) throw new Error();
      } catch { toast("No se pudo guardar el descarte en el servidor", true); return; }
    }
    x.descartado = nuevo; const abierto = $("#hall details").open; pintarHall(); $("#hall details").open = abierto; }));
  document.querySelectorAll(".hc img").forEach((im) => (im.onclick = () => visor(im.src)));
}

function visor(src) {
  const v = $("#visor"); v.querySelector("img").src = src; v.classList.remove("zoom"); v.hidden = false;
}
$("#visor img").onclick = () => $("#visor").classList.toggle("zoom");
$("#visor .cerrar").onclick = () => ($("#visor").hidden = true);

/* ---------- guardar ---------- */
function nombreBase() {
  const b = (archivo && archivo.name ? archivo.name : desdeHist ? "seguimiento" : "analisis").replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "_").slice(0, 40) || "analisis";
  return "vialidad_" + b;
}
function blobB64(blob) {
  return new Promise((ok, ko) => { const f = new FileReader(); f.onload = () => ok(String(f.result).split(",")[1]); f.onerror = ko; f.readAsDataURL(blob); });
}
async function guardarBlob(blob, nombre, mime) {
  if (enApp) {
    const b64 = await blobB64(blob);
    window.Android.saveFile(nombre, mime, b64);
    return;
  }
  const u = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = u; a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 10000); toast("Guardado: " + nombre);
}
async function guardarDataUrl(d, nombre) { const b = await (await fetch(d)).blob(); await guardarBlob(b, nombre, b.type || "image/jpeg"); }
async function descargarUrl(url, nombre) {
  if (enApp) { window.location.href = url; toast("Descargando video… revise Descargas"); return; }
  const a = document.createElement("a"); a.href = url; a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
}

/* ---------- informe PDF ---------- */
async function aDataUrl(url) {
  if (url.startsWith("data:")) return url;
  const b = await (await fetch(url)).blob();
  return new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(b); });
}
function dimImg(d) { return new Promise((ok) => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]); i.onerror = () => ok([4, 3]); i.src = d; }); }

async function informe() {
  const btn = $("#btn-pdf"); btn.disabled = true; const t0 = btn.textContent; btn.textContent = "Generando informe…";
  try {
    const { jsPDF } = window.jspdf; const doc = new jsPDF({ unit: "mm", format: "a4" });
    const W = 210, M = 14, AN = W - 2 * M; let y = M;
    const salto = (h) => { if (y + h > 285) { doc.addPage(); y = M; } };
    const texto = (t, size = 10, bold = false, color = [15, 23, 42]) => {
      doc.setFont("helvetica", bold ? "bold" : "normal"); doc.setFontSize(size); doc.setTextColor(...color);
      const l = doc.splitTextToSize(String(t), AN); salto(l.length * size * 0.4 + 1); doc.text(l, M, y + size * 0.35); y += l.length * size * 0.42 + 1.5;
    };
    const imagen = async (d, maxH = 110, ancho = AN) => {
      const [w, h] = await dimImg(d); let pw = ancho, ph = (pw * h) / w; if (ph > maxH) { ph = maxH; pw = (ph * w) / h; }
      salto(ph + 3); doc.addImage(d, "JPEG", M, y, pw, ph); y += ph + 3;
    };
    const ahora = new Date().toLocaleString("es-EC");
    doc.setFillColor(15, 23, 42); doc.rect(0, 0, W, 22, "F");
    doc.setTextColor(255, 255, 255); doc.setFont("helvetica", "bold"); doc.setFontSize(16); doc.text("Informe de daños viales", M, 14); y = 30;
    const modelo = R.tipo === "foto" ? R.j.modelo_version : R.m.modelo_version;
    const perfil = R.tipo === "foto" ? R.j.perfil : R.m.perfil, umbral = R.tipo === "foto" ? R.j.conf_umbral : R.m.conf_umbral;
    texto(`Fecha del informe: ${ahora}`); texto(`Archivo: ${archivo ? archivo.name : (R.tipo === "foto" ? R.j.archivo : R.m.archivo) || "-"}`);
    texto(`Sensibilidad: ${perfil} (umbral de confianza ${umbral}) · Modelo: ${modelo}`);
    if (R.tipo === "foto" && R.j.guardado) texto(`Guardado en el servidor: tramo «${R.j.tramo}», captura n.º ${R.j.id}`);
    if (R.tipo === "video" && R.res.guardado) texto(`Guardado en el servidor: tramo «${R.tramo || ""}», video n.º ${R.res.video_id}`);

    if (R.tipo === "foto") {
      const j = R.j; y += 2;
      texto(`Índice de severidad: ${j.indice_severidad} / 100 · Calificación: ${j.calificacion}`, 12, true);
      texto(`Daños detectados: ${j.n_detecciones}`);
      await imagen(j.imagen_anotada, 120);
      texto("Conteo por tipo", 11, true);
      const e = Object.entries(j.conteo); if (!e.length) texto("Sin daños detectados."); e.forEach(([k, n]) => texto(`• ${nom(k)}: ${n}`));
      if (j.detecciones.length) {
        texto("Detecciones", 11, true);
        j.detecciones.forEach((d, i) => texto(`${i + 1}. ${nom(d.clase)} — confianza ${Math.round(d.confianza * 100)} % — ocupa ${(d.area_frac * 100).toFixed(2)} % de la imagen`, 9));
      }
      if (j.gps_exif) texto(`Ubicación (EXIF): ${j.gps_exif.lat.toFixed(6)}, ${j.gps_exif.lon.toFixed(6)}`);
    } else {
      const m = R.m, c = conteoVivo(), tot = Object.values(c).reduce((a, b) => a + b, 0), res = R.res; y += 2;
      texto(`Modo: ${m.modo === "anotado" ? "video marcado" : "por fotogramas"} · Duración ${fmtT(m.duracion_s)} · ${m.n_frames} fotogramas analizados`);
      texto(`Índice medio: ${m.indice_medio} · máximo: ${m.indice_max} · tramo afectado: ${m.pct_afectados} % · Calificación: ${m.calificacion}`, 12, true);
      if (m.limite_aplicado) texto("Nota: el servidor redujo el detalle para no exceder el límite de fotogramas.", 9, false, [161, 98, 7]);
      texto(`Conteo estimado de daños distintos (tras descartes): ${tot}`, 11, true);
      Object.entries(c).forEach(([k, n]) => texto(`• ${nom(k)}: ${n}`));
      const descart = R.hall.filter((h) => h.descartado).length; if (descart) texto(`Descartados manualmente: ${descart}`, 9);
      const mant = R.hall.filter((h) => !h.descartado);
      if (mant.length) {
        y += 2; texto("Daños principales (miniaturas)", 11, true);
        const orden = [...mant].sort((a, b) => b.conf_max * Math.sqrt(b.area_max || 0) - a.conf_max * Math.sqrt(a.area_max || 0)).slice(0, 12);
        const cw = (AN - 6) / 3;
        for (let i = 0; i < orden.length; i += 3) {
          salto(cw * 0.75 + 12); let x = M;
          for (const h of orden.slice(i, i + 3)) {
            try { const d = await aDataUrl(h.imagen); doc.addImage(d, "JPEG", x, y, cw, cw * 0.75); } catch {}
            doc.setFontSize(8); doc.setTextColor(15, 23, 42); doc.text(`${nom(h.clase)}`, x, y + cw * 0.75 + 4);
            doc.setTextColor(100, 116, 139); doc.text(`${fmtT(h.t_ini)} · conf. ${Math.round(h.conf_max * 100)} %`, x, y + cw * 0.75 + 8); x += cw + 3;
          }
          y += cw * 0.75 + 11;
        }
      }
      const mej = (res.mejores || []).slice(0, 6);
      if (mej.length) { y += 2; texto("Fotogramas más dañados", 11, true); for (const x of mej) { texto(`${fmtT(x.t)} · índice ${x.indice}`, 9); await imagen(x.imagen, 70, AN * 0.7); } }
    }
    y += 3;
    texto("Aviso: el índice de severidad es una medida propia (heurística) basada en el área de los daños detectados; no equivale a PCI ni IRI. El modelo puede producir falsas alarmas y omitir daños, por lo que los resultados deben verificarse visualmente.", 8, false, [100, 116, 139]);
    const pdf = doc.output("blob");
    await guardarBlob(pdf, nombreBase() + "_informe.pdf", "application/pdf");
  } catch (e) { toast("No se pudo crear el informe: " + (e.message || e), true); }
  finally { btn.disabled = false; btn.textContent = t0; }
}

/* ---------- seguimientos (historial guardado en el servidor) ---------- */
function enlazarHist() { const b = $("#btn-hv"); if (b) b.onclick = () => ir("historial"); }
const fmtF = (iso) => { try { return new Date(iso).toLocaleString("es-EC", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; } };

async function cargarHistorial() {
  const sel = $("#h-tramo");
  try {
    const ts = await leer(await fetch("/api/tramos", { cache: "no-store" }));
    if (!ts.length) {
      sel.innerHTML = ""; $("#h-resumen").innerHTML = ""; $("#h-chartbox").hidden = true;
      $("#h-lista").className = "hint"; $("#h-lista").textContent = "Todavía no hay tramos. Crea uno en Ajustes (⚙) y guarda análisis en él.";
      return;
    }
    const prev = sel.value || lsGet("tramo") || "";
    sel.innerHTML = ts.map((t) => `<option value="${t.id}">${esc(t.nombre)}${t.ciudad ? " · " + esc(t.ciudad) : ""}</option>`).join("");
    if (ts.some((t) => String(t.id) === String(prev))) sel.value = prev;
    await verTramo(sel.value);
  } catch (e) { $("#h-lista").className = "hint"; $("#h-lista").textContent = "No se pudo cargar: " + (e.message || e); }
}
$("#h-tramo").addEventListener("change", () => { lsSet("tramo", $("#h-tramo").value); verTramo($("#h-tramo").value); });

async function verTramo(id) {
  $("#h-lista").className = "hint"; $("#h-lista").textContent = "Cargando…";
  let s;
  try { s = await leer(await fetch(`/api/tramos/${id}/seguimiento`, { cache: "no-store" })); }
  catch (e) { $("#h-lista").textContent = "No se pudo cargar: " + (e.message || e); return; }
  const t = s.tramo, td = s.tendencia || {};
  const ult = t.ultimo_indice != null ? `Último índice de fotos: <b>${t.ultimo_indice}</b> ${badge(t.ultima_calificacion)}` : "Sin fotos guardadas todavía.";
  $("#h-resumen").innerHTML = `<div class="rowh"><span>${t.n_capturas} ${t.n_capturas === 1 ? "foto" : "fotos"} · ${t.n_videos} ${t.n_videos === 1 ? "video" : "videos"}</span></div><div>${ult}</div>` +
    (td.mensaje ? `<div class="nota">${esc(td.mensaje)}</div>` : "") +
    ((s.perfiles || []).length > 1 ? '<div class="warn">Este tramo mezcla fotos analizadas con sensibilidades distintas: los índices no son del todo comparables.</div>' : "");
  // gráfica: índice por fecha (fotos: promedio diario; videos: índice medio)
  if (chartH) { chartH.destroy(); chartH = null; }
  const fechas = [...new Set([...(s.puntos || []).map((p) => p.fecha), ...(s.videos || []).map((v) => v.fecha)])].sort();
  $("#h-chartbox").hidden = fechas.length === 0;
  if (fechas.length) {
    const fp = Object.fromEntries((s.puntos || []).map((p) => [p.fecha, p.indice]));
    const vp = {}; (s.videos || []).forEach((v) => { vp[v.fecha] = v.indice_medio; });
    try {
      chartH = new Chart($("#h-ch"), {
        type: "line",
        data: { labels: fechas, datasets: [
          { label: "Fotos", data: fechas.map((f) => (f in fp ? fp[f] : null)), borderColor: "#f59e0b", backgroundColor: "#f59e0b", spanGaps: true, tension: .2 },
          { label: "Videos", data: fechas.map((f) => (f in vp ? vp[f] : null)), borderColor: "#2563eb", backgroundColor: "#2563eb", showLine: false, pointRadius: 5 },
        ] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } }, scales: { y: { min: 0, max: 100 }, x: { ticks: { maxTicksLimit: 5 } } } },
      });
    } catch {}
  }
  const items = [
    ...(s.capturas || []).map((c) => ({ tipo: "foto", id: c.id, f: c.fecha_captura, idx: c.indice_severidad, cal: c.calificacion, img: c.url_anotada, extra: `${c.n_detecciones} daños` })),
    ...(s.videos || []).map((v) => ({ tipo: "video", id: v.id, f: v.fecha_inicio, idx: v.indice_medio, cal: v.calificacion, img: null, extra: `${fmtT(v.duracion_s)} · ${v.n_frames} fotogramas` })),
  ].sort((a, b) => new Date(b.f) - new Date(a.f));
  $("#h-lista").className = "";
  $("#h-lista").innerHTML = items.length
    ? items.map((it, i) => `<div class="it" data-i="${i}">${it.img ? `<img src="${it.img}" loading="lazy" alt="">` : '<div class="ph">🎥</div>'}<div class="tx"><b>${it.tipo === "foto" ? "Foto" : "Video"}</b> · ${esc(fmtF(it.f))}<small>índice ${it.idx} · ${esc(it.extra)}</small>${badge(it.cal)}</div></div>`).join("")
    : '<p class="hint">Este tramo todavía no tiene análisis guardados.</p>';
  document.querySelectorAll("#h-lista .it").forEach((el) => (el.onclick = () => abrirItem(items[+el.dataset.i], t)));
}

async function abrirItem(it, t) {
  try {
    toast("Abriendo…");
    limpiarResultado(); desdeHist = true; archivo = null;
    if (it.tipo === "foto") {
      const c = await leer(await fetch("/api/capturas/" + it.id, { cache: "no-store" }));
      mostrarFoto(capturaAFoto(c, { nombre: t.nombre }));
    } else {
      const res = await leer(await fetch("/api/videos/" + it.id, { cache: "no-store" }));
      await mostrarVideo(res, { nombre: t.nombre });
    }
    agregarBorrar(it);
    ir("detalle");
  } catch (e) { desdeHist = false; toast("No se pudo abrir: " + (e.message || e), true); }
}

function agregarBorrar(it) {
  const card = document.querySelector("#v-resultado .card");
  const b = document.createElement("button");
  b.type = "button"; b.className = "btn ghost"; b.textContent = "Eliminar este análisis del servidor";
  let armado = false, h;
  b.onclick = async () => {
    if (!armado) {
      armado = true; b.textContent = "Pulsa otra vez para confirmar"; b.style.background = "#fee2e2";
      h = setTimeout(() => { armado = false; b.textContent = "Eliminar este análisis del servidor"; b.style.background = ""; }, 4000);
      return;
    }
    clearTimeout(h);
    try {
      const r = await fetch((it.tipo === "foto" ? "/api/capturas/" : "/api/videos/") + it.id, { method: "DELETE" });
      if (!r.ok) throw new Error("Error " + r.status);
      toast("Análisis eliminado"); limpiarResultado(); ir("historial");
    } catch (e) { toast("No se pudo eliminar: " + (e.message || e), true); }
  };
  card.appendChild(b);
}

/* ---------- inicio ---------- */
estado(); cargarConfig(); actualizarHints(); actualizarDest();
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
