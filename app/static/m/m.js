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
let chart = null;

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
if (enApp) { $("#btn-srv").hidden = false; $("#btn-srv").onclick = () => window.Android.changeServer(); }

/* ---------- selección ---------- */
function elegir(file) {
  if (!file) return;
  limpiarResultado();
  archivo = file; esVideo = file.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|3gp|mkv)$/i.test(file.name);
  if (urlPrevia) URL.revokeObjectURL(urlPrevia);
  urlPrevia = URL.createObjectURL(file);
  const mb = (file.size / 1048576).toFixed(1);
  $("#previa").innerHTML = (esVideo ? `<video src="${urlPrevia}#t=0.1" muted playsinline preload="metadata"></video>` : `<img src="${urlPrevia}" alt="">`) +
    `<div><b>${esc(file.name || (esVideo ? "video" : "foto"))}</b><small>${esVideo ? "Video" : "Foto"} · ${mb} MB</small></div>`;
  $("#previa").hidden = false; $("#opciones").hidden = false; $("#o-video").hidden = !esVideo;
  actualizarHints();
}
["#in-foto", "#in-video", "#in-gal"].forEach((s) => $(s).addEventListener("change", (e) => { elegir(e.target.files[0]); e.target.value = ""; }));

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
  aviso(""); limpiarResultado(); cancelado = false; jobId = null;
  vista("p"); progreso(null, "Subiendo al servidor…", esVideo ? "Analizando video…" : "Analizando foto…");
  window.scrollTo(0, 0);
  const fd = new FormData();
  fd.append("file", archivo, archivo.name || (esVideo ? "video.mp4" : "foto.jpg"));
  fd.append("sensibilidad", $("#o-sens").value);
  abortar = new AbortController();
  try {
    if (!esVideo) {
      const r = await fetch("/api/analizar", { method: "POST", body: fd, signal: abortar.signal });
      const j = await leer(r);
      mostrarFoto(j);
    } else {
      fd.append("modo", modo()); fd.append("guardar", "false");
      fd.append("cada_n", $("#o-cada").value); fd.append("intervalo_s", $("#o-int").value);
      const r = await fetch("/api/videos", { method: "POST", body: fd, signal: abortar.signal });
      const { job_id } = await leer(r);
      jobId = job_id;
      const res = await esperar(job_id);
      await mostrarVideo(res);
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

function mostrarFoto(j) {
  R = { tipo: "foto", j };
  const cal = j.calificacion;
  $("#v-resultado").innerHTML = `
  <div class="card">
    <h2>Resultado</h2>
    <img class="resimg" id="img-res" src="${j.imagen_anotada}" alt="Foto con daños marcados">
    <div class="kpis">
      <div><span>Índice de severidad</span><b>${j.indice_severidad}</b></div>
      <div><span>Calificación</span>${badge(cal)}</div>
      <div><span>Daños detectados</span><b>${j.n_detecciones}</b></div>
      <div><span>Tiempo</span><b>${(j.tiempo_inferencia_ms / 1000).toFixed(1)} s</b></div>
    </div>
    ${chips(j.conteo)}
    ${NOTA}
    <button class="btn prim" id="btn-pdf">Guardar informe (PDF)</button>
    <button class="btn dark" id="btn-img">Guardar foto marcada</button>
  </div>`;
  $("#v-resultado").hidden = false;
  $("#img-res").onclick = () => visor(j.imagen_anotada);
  $("#btn-pdf").onclick = () => informe();
  $("#btn-img").onclick = () => guardarDataUrl(j.imagen_anotada, nombreBase() + "_marcada.jpg");
  $("#v-resultado").scrollIntoView({ behavior: "smooth" });
}

function conteoVivo() {
  const c = {};
  R.hall.forEach((h) => { if (!h.descartado) c[h.clase] = (c[h.clase] || 0) + 1; });
  return c;
}

async function mostrarVideo(res) {
  const m = res.resumen;
  R = { tipo: "video", res, m, hall: (res.hallazgos || []).map((h) => ({ ...h })) };
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
    <h3>Conteo estimado de daños distintos: <span id="tot">0</span></h3>
    <div id="cont"></div>
    <p class="hint">Una misma grieta o bache puede contarse más de una vez, o dos daños distintos juntarse. Toque ✕ en una foto para descartar una falsa alarma y el conteo baja.</p>
    <div id="hall"></div>
    ${mejores}
    <h3>Evolución del índice</h3><div class="chartbox"><canvas id="ch"></canvas></div>
    ${NOTA}
    <button class="btn prim" id="btn-pdf">Guardar informe (PDF)</button>
    ${res.video_url ? '<button class="btn dark" id="btn-vid">Guardar video marcado</button>' : ""}
  </div>`;
  $("#v-resultado").hidden = false;
  pintarHall();
  $("#btn-pdf").onclick = () => informe();
  const bv = $("#btn-vid"); if (bv) bv.onclick = () => descargarUrl(res.video_url, nombreBase() + "_marcado.mp4");
  document.querySelectorAll(".tira img").forEach((im) => (im.onclick = () => visor(im.src)));
  try {
    chart = new Chart($("#ch"), { type: "line", data: { labels: res.serie.map((s) => fmtT(s.t)), datasets: [{ data: res.serie.map((s) => s.indice), borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,.15)", fill: true, pointRadius: 0, tension: .25 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100 }, x: { ticks: { maxTicksLimit: 6 } } } } });
  } catch {}
  $("#v-resultado").scrollIntoView({ behavior: "smooth" });
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
  document.querySelectorAll(".hx").forEach((b) => (b.onclick = () => { const x = R.hall[+b.dataset.i]; x.descartado = !x.descartado; const abierto = $("#hall details").open; pintarHall(); $("#hall details").open = abierto; }));
  document.querySelectorAll(".hc img").forEach((im) => (im.onclick = () => visor(im.src)));
}

function visor(src) {
  const v = $("#visor"); v.querySelector("img").src = src; v.classList.remove("zoom"); v.hidden = false;
}
$("#visor img").onclick = () => $("#visor").classList.toggle("zoom");
$("#visor .cerrar").onclick = () => ($("#visor").hidden = true);

/* ---------- guardar ---------- */
function nombreBase() {
  const b = (archivo && archivo.name ? archivo.name : "analisis").replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "_").slice(0, 40) || "analisis";
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
    texto(`Fecha del informe: ${ahora}`); texto(`Archivo: ${archivo ? archivo.name : "-"}`);
    texto(`Sensibilidad: ${perfil} (umbral de confianza ${umbral}) · Modelo: ${modelo}`);

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

/* ---------- inicio ---------- */
estado(); actualizarHints();
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
