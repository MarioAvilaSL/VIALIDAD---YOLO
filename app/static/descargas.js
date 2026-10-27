/* Descarga del análisis como ZIP (se arma en el navegador, así funciona también con «Solo analizar»,
   donde el servidor no guarda nada). Contenido: imagen o muestras marcadas, informe.html, datos en CSV y JSON. */
const H = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NUM = (v, d = 2) => (v == null || Number.isNaN(v) ? "" : Number(v).toFixed(d).replace(".", ","));
const csvCell = (v) => { const s = String(v ?? ""); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const csv = (cols, rows) => "﻿" + [cols.join(";"), ...rows.map((r) => r.map(csvCell).join(";"))].join("\r\n");
const osm = (lat, lon) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`;
const tmin = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const stamp = () => { const d = new Date(), p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`; };
const base = (n) => String(n || "analisis").replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_").slice(0, 40) || "analisis";

async function blobDe(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("No se pudo obtener " + url.slice(0, 40));
  return r.blob();
}
function bajar(blob, nombre) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
const ESTILO = `body{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#0f172a}
h1{font-size:22px}h2{font-size:17px;margin-top:28px}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border:1px solid #e2e8f0;padding:5px 8px;text-align:left}th{background:#f1f5f9}img{max-width:100%;border-radius:8px}
.k{display:flex;gap:10px;flex-wrap:wrap}.k div{border:1px solid #e2e8f0;border-radius:8px;padding:8px 14px}.k span{display:block;font-size:12px;color:#64748b}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}.g figure{margin:0;border:1px solid #e2e8f0;border-radius:8px;padding:8px}
.n{background:#f8fafc;border-left:4px solid #94a3b8;padding:8px 12px;font-size:13px;color:#334155}`;
const NOTA = "El índice de severidad es una heurística propia (no es PCI ni IRI): solo es comparable entre análisis del mismo tramo, con la misma sensibilidad y el mismo encuadre. " +
  "Las detecciones son automáticas y pueden incluir falsas alarmas y omitir daños.";
const pagina = (titulo, cuerpo) => `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${H(titulo)}</title><style>${ESTILO}</style></head><body>${cuerpo}</body></html>`;
const filas = (pares) => `<table>${pares.filter((p) => p[1] != null && p[1] !== "").map(([a, b]) => `<tr><th style="width:34%">${H(a)}</th><td>${b}</td></tr>`).join("")}</table>`;

async function descargarCaptura(c, boton) {
  const txt = boton?.textContent; if (boton) { boton.disabled = true; boton.textContent = "Preparando…"; }
  try {
    const zip = new JSZip(), n = base(c.archivo_original);
    zip.file("foto_marcada.jpg", await blobDe(c.url_anotada));
    zip.file("foto_original.jpg", await blobDe(c.url_imagen));
    const dets = c.detecciones || [];
    zip.file("detecciones.csv", csv(["clase", "confianza_%", "area_%_imagen", "x1", "y1", "x2", "y2"],
      dets.map((d) => [nombreClase(d.clase), NUM(d.confianza * 100, 1), NUM(d.area_frac * 100, 2), Math.round(d.x1), Math.round(d.y1), Math.round(d.x2), Math.round(d.y2)])));
    const datos = { archivo: c.archivo_original, tramo: c.solo ? null : c.tramo_nombre, guardado: !c.solo, fecha_captura: c.fecha_captura, origen_fecha: c.origen_fecha,
      gps: c.lat != null ? { lat: c.lat, lon: c.lon, origen: c.origen_gps } : null, indice_severidad: c.indice_severidad, calificacion: c.calificacion,
      conteo: c.conteo, sensibilidad: c.perfil, umbral: c.conf_umbral, parametros: c.parametros ? JSON.parse(c.parametros) : null, modelo: c.modelo_version,
      ancho: c.ancho, alto: c.alto, notas: c.notas, detecciones: dets };
    zip.file("analisis.json", JSON.stringify(datos, null, 2));
    const gps = c.lat != null ? `<a href="${osm(c.lat, c.lon)}">${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}</a> (${c.origen_gps === "exif" ? "EXIF de la foto" : "manual"})` : "Sin GPS";
    zip.file("informe.html", pagina("Informe de foto · " + c.archivo_original, `<h1>Análisis de foto</h1>
      ${filas([["Archivo", H(c.archivo_original)], ["Tramo", c.solo ? "Sin guardar" : H(c.tramo_nombre)], ["Fecha", c.fecha_captura ? H(fmtDT(c.fecha_captura)) : ""],
        ["Ubicación", gps], ["Índice de severidad", `<b>${c.indice_severidad.toFixed(1)}</b> / 100 · ${H(c.calificacion)}`],
        ["Sensibilidad", `${H(c.perfil)} · umbral ${H(c.conf_umbral)}`], ["Modelo", H(c.modelo_version)], ["Notas", H(c.notas)]])}
      <h2>Foto con daños marcados</h2><img src="foto_marcada.jpg" alt="Foto marcada">
      <h2>Detecciones (${dets.length})</h2>
      ${dets.length ? `<table><tr><th>Daño</th><th>Confianza</th><th>% de la imagen</th></tr>${dets.map((d) => `<tr><td>${H(nombreClase(d.clase))}</td><td>${(d.confianza * 100).toFixed(0)}%</td><td>${(d.area_frac * 100).toFixed(1)}%</td></tr>`).join("")}</table>` : "<p>Sin daños detectados con este umbral.</p>"}
      <p class="n">${H(NOTA)}</p>`));
    bajar(await zip.generateAsync({ type: "blob" }), `analisis_${n}_${stamp()}.zip`);
  } catch (e) { toast("No se pudo preparar la descarga: " + e.message, "err"); }
  finally { if (boton) { boton.disabled = false; boton.textContent = txt; } }
}

async function descargarVideo(res, boton) {
  const txt = boton?.textContent; if (boton) { boton.disabled = true; boton.textContent = "Preparando…"; }
  try {
    const r = res.resumen, zip = new JSZip(), n = base(r.archivo);
    const hall = res.hallazgos || [], vivos = hall.filter((h) => !h.descartado);
    const cuenta = {}; vivos.forEach((h) => (cuenta[h.clase] = (cuenta[h.clase] || 0) + 1));
    for (let i = 0; i < res.mejores.length; i++) zip.file(`muestras/fotograma_${String(i + 1).padStart(2, "0")}_${tmin(res.mejores[i].t).replace(":", "m")}s.jpg`, await blobDe(res.mejores[i].imagen));
    for (let i = 0; i < vivos.length; i++) zip.file(`danos/dano_${String(i + 1).padStart(3, "0")}_${vivos[i].clase}_${tmin(vivos[i].t_ini).replace(":", "m")}s.jpg`, await blobDe(vivos[i].imagen));
    zip.file("serie_indice.csv", csv(["segundo", "minuto", "indice", "n_detecciones", "conteo"], res.serie.map((m) => [NUM(m.t, 2), tmin(m.t), NUM(m.indice, 1), m.n, Object.entries(m.conteo).map(([k, v]) => `${nombreClase(k)}:${v}`).join(" | ")])));
    if (r.modo === "anotado") zip.file("danos.csv", csv(["n", "clase", "estado", "desde_s", "hasta_s", "veces_detectado", "conf_max_%", "area_max_%", "lat", "lon"],
      hall.map((h, i) => [i + 1, nombreClase(h.clase), h.descartado ? "descartado" : "conservado", NUM(h.t_ini), NUM(h.t_fin), h.n_apariciones, NUM(h.conf_max * 100, 1), NUM(h.area_max * 100, 2), h.lat ?? "", h.lon ?? ""])));
    const feats = [];
    if (res.ruta?.length > 1) feats.push({ type: "Feature", properties: { tipo: "ruta" }, geometry: { type: "LineString", coordinates: res.ruta.map(([la, lo]) => [lo, la]) } });
    vivos.filter((h) => h.lat != null).forEach((h, i) => feats.push({ type: "Feature", properties: { tipo: "dano", clase: nombreClase(h.clase), t_ini_s: h.t_ini }, geometry: { type: "Point", coordinates: [h.lon, h.lat] } }));
    if (feats.length) zip.file("ruta.geojson", JSON.stringify({ type: "FeatureCollection", features: feats }, null, 2));
    zip.file("analisis.json", JSON.stringify({ resumen: r, conteo_estimado: cuenta, hallazgos: hall.map(({ imagen, ...h }) => h), serie: res.serie, muestras: res.mejores.map(({ imagen, ...m }) => m), ruta: res.ruta }, null, 2));
    const galeria = res.mejores.map((m, i) => `<figure><img src="muestras/fotograma_${String(i + 1).padStart(2, "0")}_${tmin(m.t).replace(":", "m")}s.jpg"><figcaption>${tmin(m.t)} · índice ${m.indice.toFixed(1)}${m.lat != null ? ` · <a href="${osm(m.lat, m.lon)}">ubicación</a>` : ""}</figcaption></figure>`).join("");
    const gDanos = vivos.map((h, i) => `<figure><img src="danos/dano_${String(i + 1).padStart(3, "0")}_${h.clase}_${tmin(h.t_ini).replace(":", "m")}s.jpg"><figcaption><b>${H(nombreClase(h.clase))}</b> · ${tmin(h.t_ini)} · visto ${h.n_apariciones} veces${h.lat != null ? ` · <a href="${osm(h.lat, h.lon)}">ubicación</a>` : ""}</figcaption></figure>`).join("");
    const conteoTxt = Object.entries(cuenta).map(([k, v]) => `${H(nombreClase(k))}: <b>${v}</b>`).join(" · ") || "ninguno";
    zip.file("informe.html", pagina("Informe de video · " + r.archivo, `<h1>Análisis de video</h1>
      <div class="k"><div><span>Calificación</span><b>${H(r.calificacion)}</b></div><div><span>Índice medio</span><b>${r.indice_medio.toFixed(1)}</b></div><div><span>Índice máximo</span><b>${r.indice_max.toFixed(1)}</b></div><div><span>Con daños</span><b>${r.pct_afectados.toFixed(0)}%</b></div>${r.modo === "anotado" ? `<div><span>Baches (estimado)</span><b>${cuenta.pothole || 0}</b></div>` : ""}</div>
      ${filas([["Archivo", H(r.archivo)], ["Modo", r.modo === "anotado" ? `Video marcado · 1 de cada ${r.cada_n} fotogramas` : `Por fotogramas · 1 cada ${r.intervalo_s} s`],
        ["Duración", tmin(r.duracion_s)], ["Fotogramas analizados", r.n_frames], ["Sensibilidad", `${H(r.perfil)}`], ["Modelo", H(r.modelo_version)], ["Tiempo de proceso", `${r.tiempo_proceso_s} s`],
        ["Ruta GPS", res.ruta ? `Incluida (cubre ${r.gps_cubre_pct ?? "?"}% de los análisis) · ver ruta.geojson` : "Sin GPX"]])}
      ${r.modo === "anotado" ? `<h2>Daños distintos estimados</h2><p>${conteoTxt}</p><p class="n">Conteo estimado por seguimiento entre fotogramas: puede unir dos daños cercanos o separar uno en dos. Los daños descartados a mano no se cuentan (${hall.length - vivos.length} descartados). Detalle en danos.csv.</p><div class="g">${gDanos}</div>` : ""}
      <h2>Fotogramas más críticos</h2><div class="g">${galeria || "<p>Ningún fotograma con daños.</p>"}</div>
      <p class="n">${H(NOTA)} Este informe no incluye el video; descárgalo aparte si lo necesitas.</p>`));
    bajar(await zip.generateAsync({ type: "blob" }), `analisis_video_${n}_${stamp()}.zip`);
  } catch (e) { toast("No se pudo preparar la descarga: " + e.message, "err"); }
  finally { if (boton) { boton.disabled = false; boton.textContent = txt; } }
}
window.descargarCaptura = descargarCaptura;
window.descargarVideo = descargarVideo;
