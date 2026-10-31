package ec.vialidad.app;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.media.MediaRecorder;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Size;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;

/**
 * Graba el recorrido: video (H.264, sin audio) + ruta GPS en un GPX con la misma hora del teléfono.
 * Todo queda en la caché de la app (carpeta "recorridos"); MainActivity lo entrega a la página web.
 * Esta pantalla se queda en primer plano mientras graba, por eso el GPS sigue llegando sin servicios extra.
 */
public class RecorridoActivity extends Activity implements TextureView.SurfaceTextureListener {

    public static final String EXTRA_VIDEO = "video";
    public static final String EXTRA_GPX = "gpx";
    public static final String EXTRA_INICIO = "inicio_ms";
    public static final String EXTRA_DUR = "dur_s";
    public static final String EXTRA_PUNTOS = "puntos";
    public static final String EXTRA_ERROR = "error";
    public static final String EXTRA_SERVIDOR = "servidor";   // entrada: URL del servidor
    public static final String EXTRA_SENS = "sens";           // entrada: normal | sensible
    public static final String EXTRA_VIVO = "vivo";           // entrada: analizar en vivo
    public static final String EXTRA_CONTEO = "conteo_vivo";  // salida: JSON con el conteo estimado

    private static final int REQ_PERMISOS = 2001;
    private static final long MAX_MS = 15 * 60 * 1000L;       // ≈ 340 MB a 3 Mbps; el servidor admite 500 MB
    private static final int BITRATE = 3_000_000;
    private static final int ANCHO_MAX = 1280;

    /** TextureView que respeta la relación de aspecto de la cámara. */
    private static class AutoFit extends TextureView {
        private int rw, rh;
        AutoFit(Context c) { super(c); }
        void setAspect(int w, int h) { rw = w; rh = h; requestLayout(); }
        @Override
        protected void onMeasure(int wSpec, int hSpec) {
            int w = View.MeasureSpec.getSize(wSpec), h = View.MeasureSpec.getSize(hSpec);
            int[] m = ajustar(w, h, rw, rh);
            setMeasuredDimension(m[0], m[1]);
        }
    }

    /** Calcula el tamaño que cabe en (w,h) manteniendo la relación rw:rh. */
    private static int[] ajustar(int w, int h, int rw, int rh) {
        if (rw == 0 || rh == 0) return new int[]{w, h};
        if (w * rh > h * rw) return new int[]{h * rw / rh, h};
        return new int[]{w, w * rh / rw};
    }

    /** Detección normalizada (0..1) para dibujar y contar. */
    private static class Det {
        String clase; float conf, x1, y1, x2, y2;
        float cx() { return (x1 + x2) / 2f; }
        float cy() { return (y1 + y2) / 2f; }
    }

    private static String etiqueta(String c) {
        switch (c) {
            case "pothole": return "bache";
            case "alligator_crack": return "piel de cocodrilo";
            case "transverse_crack": return "transversal";
            case "longitudinal_crack": return "longitudinal";
            default: return c;
        }
    }

    private static int colorClase(String c) {
        switch (c) {
            case "pothole": return 0xFFEF4444;
            case "alligator_crack": return 0xFFF97316;
            case "transverse_crack": return 0xFF3B82F6;
            default: return 0xFFFACC15;
        }
    }

    /** Capa transparente que dibuja las cajas encima de la vista previa (misma medida que ella). */
    private static class Capa extends View {
        private int rw, rh;
        private List<Det> dets = new ArrayList<>();
        private final Paint pc = new Paint(Paint.ANTI_ALIAS_FLAG), pt = new Paint(Paint.ANTI_ALIAS_FLAG), pf = new Paint();
        Capa(Context c) {
            super(c);
            pc.setStyle(Paint.Style.STROKE); pc.setStrokeWidth(5f);
            pt.setTextSize(30f); pt.setColor(Color.WHITE);
            pf.setStyle(Paint.Style.FILL);
        }
        void setAspect(int w, int h) { rw = w; rh = h; requestLayout(); }
        void poner(List<Det> d) { dets = d; postInvalidate(); }
        @Override protected void onMeasure(int ws, int hs) {
            int[] m = ajustar(View.MeasureSpec.getSize(ws), View.MeasureSpec.getSize(hs), rw, rh);
            setMeasuredDimension(m[0], m[1]);
        }
        @Override protected void onDraw(Canvas cv) {
            int w = getWidth(), h = getHeight();
            for (Det d : dets) {
                int col = colorClase(d.clase);
                pc.setColor(col);
                RectF r = new RectF(d.x1 * w, d.y1 * h, d.x2 * w, d.y2 * h);
                cv.drawRect(r, pc);
                String t = etiqueta(d.clase) + " " + Math.round(d.conf * 100) + "%";
                float tw = pt.measureText(t);
                pf.setColor(col);
                float ty = Math.max(r.top, 34f);
                cv.drawRect(r.left, ty - 34f, r.left + tw + 12f, ty + 4f, pf);
                cv.drawText(t, r.left + 6f, ty - 6f, pt);
            }
        }
    }

    private AutoFit tv;
    private Capa capa;
    private TextView conteoTxt;
    private TextView info;
    private Button btn;

    private CameraDevice cam;
    private CameraCaptureSession sesion;
    private MediaRecorder rec;
    private HandlerThread hilo;
    private Handler hCam;
    private final Handler ui = new Handler(Looper.getMainLooper());

    private Size tamVideo, tamPrev;
    private int orientSensor = 90;
    private File carpeta, archivoVideo;

    private boolean grabando = false, terminando = false, camaraAbierta = false;
    private long inicioMs, inicioElapsed;

    private LocationManager lm;
    private LocationListener oyenteGps;
    private final List<double[]> pts = new ArrayList<>();   // {ms, lat, lon}
    private long ultimoPuntoMs = 0;
    private float ultimaPrecision = -1;

    /* ------------------------------------------------------------------ ciclo de vida */

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        servidor = getIntent().getStringExtra(EXTRA_SERVIDOR);
        sens = getIntent().getStringExtra(EXTRA_SENS);
        if (sens == null) sens = "normal";
        vivoPedido = getIntent().getBooleanExtra(EXTRA_VIVO, false) && servidor != null && !servidor.isEmpty();
        carpeta = new File(getCacheDir(), "recorridos");
        //noinspection ResultOfMethodCallIgnored
        carpeta.mkdirs();

        FrameLayout raiz = new FrameLayout(this);
        raiz.setBackgroundColor(Color.BLACK);
        tv = new AutoFit(this);
        tv.setSurfaceTextureListener(this);
        raiz.addView(tv, new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER));

        capa = new Capa(this);
        raiz.addView(capa, new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER));

        conteoTxt = new TextView(this);
        conteoTxt.setTextColor(Color.WHITE);
        conteoTxt.setTextSize(14);
        conteoTxt.setPadding(28, 14, 28, 14);
        conteoTxt.setBackgroundColor(0x99000000);
        conteoTxt.setVisibility(View.GONE);
        FrameLayout.LayoutParams lc = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        lc.setMargins(0, 0, 0, 240);
        raiz.addView(conteoTxt, lc);

        info = new TextView(this);
        info.setTextColor(Color.WHITE);
        info.setTextSize(15);
        info.setPadding(28, 36, 28, 20);
        info.setBackgroundColor(0x99000000);
        info.setText("Preparando cámara…");
        raiz.addView(info, new FrameLayout.LayoutParams(-1, -2, Gravity.TOP));

        btn = new Button(this);
        btn.setText("● Iniciar grabación");
        btn.setTextSize(18);
        btn.setEnabled(false);
        btn.setOnClickListener(v -> { if (grabando) detener(); else iniciar(); });
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-1, 150, Gravity.BOTTOM);
        lp.setMargins(40, 0, 40, 60);
        raiz.addView(btn, lp);

        setContentView(raiz);

        if (!tienePermiso(Manifest.permission.CAMERA)) {
            requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION}, REQ_PERMISOS);
        } else if (!tienePermiso(Manifest.permission.ACCESS_FINE_LOCATION)) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, REQ_PERMISOS);
        } else {
            iniciarGps();
        }
    }

    private boolean tienePermiso(String p) { return checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED; }

    @Override
    public void onRequestPermissionsResult(int req, String[] permisos, int[] res) {
        super.onRequestPermissionsResult(req, permisos, res);
        if (req != REQ_PERMISOS) return;
        if (!tienePermiso(Manifest.permission.CAMERA)) { terminarConError("Sin permiso de cámara. Actívalo en Ajustes del teléfono > Apps > Vialidad."); return; }
        iniciarGps();
        if (tv.isAvailable() && !camaraAbierta) abrirCamara();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hilo = new HandlerThread("camara");
        hilo.start();
        hCam = new Handler(hilo.getLooper());
        if (tv.isAvailable() && tienePermiso(Manifest.permission.CAMERA) && !camaraAbierta && !terminando) abrirCamara();
    }

    @Override
    protected void onPause() {
        if (grabando) detener();          // si el usuario sale mientras graba, se conserva lo grabado
        else cerrarCamara();
        if (hilo != null) { hilo.quitSafely(); hilo = null; hCam = null; }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        detenerGps();
        ui.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (grabando) { detener(); return; }
        setResult(RESULT_CANCELED);
        finish();
    }

    /* ------------------------------------------------------------------ análisis en vivo (opcional) */

    private String servidor, sens = "normal";
    private boolean vivoPedido = false, vivoActivo = false;
    private HandlerThread hiloVivo;
    private Handler hVivo;
    private final int[] conteoClase = new int[4];            // bache, cocodrilo, transversal, longitudinal
    private List<Det> previas1 = new ArrayList<>(), previas2 = new ArrayList<>();
    private long ultimaRespuestaMs = 0, ultimoErrorMs = 0;
    private int ultimaLatencia = -1, enFotograma = 0;
    private String estadoPc = "";

    private static int indiceClase(String c) {
        switch (c) {
            case "pothole": return 0;
            case "alligator_crack": return 1;
            case "transverse_crack": return 2;
            default: return 3;
        }
    }

    private void iniciarVivo() {
        if (!vivoPedido || vivoActivo || terminando) return;
        vivoActivo = true;
        hiloVivo = new HandlerThread("vivo");
        hiloVivo.start();
        hVivo = new Handler(hiloVivo.getLooper());
        conteoTxt.setVisibility(View.VISIBLE);
        estadoPc = "PC: conectando…";
        refrescarConteo();
        ui.postDelayed(ciclo, 800);
    }

    private void detenerVivo() {
        vivoActivo = false;
        ui.removeCallbacks(ciclo);
        if (hiloVivo != null) { hiloVivo.quitSafely(); hiloVivo = null; hVivo = null; }
    }

    private final Runnable ciclo = new Runnable() {
        @Override public void run() {
            if (!vivoActivo || terminando || tv == null || !tv.isAvailable() || tamPrev == null) return;
            final long t0 = SystemClock.elapsedRealtime();
            final int w = 540, h = Math.round(540f * tamPrev.getWidth() / tamPrev.getHeight());
            Bitmap bm = null;
            try { bm = tv.getBitmap(w, h); } catch (Exception ignorada) { }
            final Handler hv = hVivo;
            if (bm == null || hv == null) { ui.postDelayed(this, 1000); return; }
            final Bitmap fb = bm;
            hv.post(() -> {
                List<Det> res = null;
                String err = null;
                int ms = -1;
                try {
                    ByteArrayOutputStream bo = new ByteArrayOutputStream();
                    fb.compress(Bitmap.CompressFormat.JPEG, 80, bo);
                    JSONObject j = enviar(bo.toByteArray());
                    res = new ArrayList<>();
                    int aw = Math.max(1, j.optInt("ancho", w)), ah = Math.max(1, j.optInt("alto", h));
                    JSONArray a = j.getJSONArray("detecciones");
                    for (int i = 0; i < a.length(); i++) {
                        JSONObject o = a.getJSONObject(i);
                        Det d = new Det();
                        d.clase = o.getString("clase");
                        d.conf = (float) o.optDouble("confianza", 0);
                        d.x1 = (float) (o.getDouble("x1") / aw); d.x2 = (float) (o.getDouble("x2") / aw);
                        d.y1 = (float) (o.getDouble("y1") / ah); d.y2 = (float) (o.getDouble("y2") / ah);
                        res.add(d);
                    }
                    ms = (int) Math.round(j.optDouble("tiempo_inferencia_ms", -1));
                } catch (Exception e) {
                    err = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                } finally {
                    fb.recycle();
                }
                final List<Det> r = res; final String e2 = err; final int ms2 = ms;
                final long dur = SystemClock.elapsedRealtime() - t0;
                ui.post(() -> {
                    if (!vivoActivo) return;
                    if (r != null) alRecibir(r, ms2, (int) dur); else alFallar(e2);
                    ui.postDelayed(ciclo, Math.max(150, 1000 - dur));
                });
            });
        }
    };

    /** POST multipart a /api/analizar_vivo; devuelve el JSON de respuesta. */
    private JSONObject enviar(byte[] jpg) throws Exception {
        String b = "----vialidad" + System.nanoTime();
        HttpURLConnection c = (HttpURLConnection) new URL(servidor + "/api/analizar_vivo").openConnection();
        c.setConnectTimeout(2500);
        c.setReadTimeout(9000);
        c.setDoOutput(true);
        c.setRequestMethod("POST");
        c.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + b);
        String ck = CookieManager.getInstance().getCookie(servidor);
        if (ck != null) c.setRequestProperty("Cookie", ck);
        try (OutputStream o = c.getOutputStream()) {
            o.write(("--" + b + "\r\nContent-Disposition: form-data; name=\"sensibilidad\"\r\n\r\n" + sens + "\r\n").getBytes(StandardCharsets.UTF_8));
            o.write(("--" + b + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"f.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            o.write(jpg);
            o.write(("\r\n--" + b + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }
        int code = c.getResponseCode();
        if (code != 200) throw new Exception(code == 401 ? "sin acceso (token)" : "servidor respondió " + code);
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            return new JSONObject(bo.toString("UTF-8"));
        } finally {
            c.disconnect();
        }
    }

    private boolean esMismo(Det d, List<Det> previas) {
        for (Det p : previas) {
            if (!p.clase.equals(d.clase)) continue;
            // Mismo daño si se solapa, o si estaba más arriba en la imagen (el vehículo avanza y el daño "baja").
            float ix = Math.max(0, Math.min(d.x2, p.x2) - Math.max(d.x1, p.x1));
            float iy = Math.max(0, Math.min(d.y2, p.y2) - Math.max(d.y1, p.y1));
            float inter = ix * iy, uni = (d.x2 - d.x1) * (d.y2 - d.y1) + (p.x2 - p.x1) * (p.y2 - p.y1) - inter;
            if (uni > 0 && inter / uni > 0.25f) return true;
            float dy = d.cy() - p.cy();
            if (Math.abs(d.cx() - p.cx()) < 0.15f && dy > -0.03f && dy < 0.45f) return true;
        }
        return false;
    }

    private void alRecibir(List<Det> r, int msServidor, int msTotal) {
        ultimaRespuestaMs = System.currentTimeMillis();
        ultimaLatencia = msTotal;
        enFotograma = r.size();
        estadoPc = "PC: ✓ " + msTotal + " ms";
        if (grabando) {
            for (Det d : r) {
                if (!esMismo(d, previas1) && !esMismo(d, previas2)) conteoClase[indiceClase(d.clase)]++;
            }
            previas2 = previas1;
            previas1 = r;
        }
        capa.poner(r);
        refrescarConteo();
    }

    private void alFallar(String e) {
        ultimoErrorMs = System.currentTimeMillis();
        estadoPc = "PC: sin conexión (" + e + ")";
        if (ultimaRespuestaMs == 0 || ultimoErrorMs - ultimaRespuestaMs > 3000) capa.poner(new ArrayList<>());
        refrescarConteo();
    }

    private int totalVivo() { return conteoClase[0] + conteoClase[1] + conteoClase[2] + conteoClase[3]; }

    private void refrescarConteo() {
        if (!vivoPedido) return;
        conteoTxt.setText(String.format(Locale.US,
                "En vivo · %s · ahora: %d\nDaños distintos (estimado): %d\nbache %d · cocodrilo %d · transv. %d · long. %d",
                estadoPc, enFotograma, totalVivo(), conteoClase[0], conteoClase[1], conteoClase[2], conteoClase[3]));
    }

    private String conteoJson() {
        try {
            JSONObject o = new JSONObject();
            o.put("pothole", conteoClase[0]); o.put("alligator_crack", conteoClase[1]);
            o.put("transverse_crack", conteoClase[2]); o.put("longitudinal_crack", conteoClase[3]);
            return o.toString();
        } catch (Exception e) { return ""; }
    }

    /* ------------------------------------------------------------------ GPS */

    private void iniciarGps() {
        if (oyenteGps != null || !tienePermiso(Manifest.permission.ACCESS_FINE_LOCATION)) return;
        lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        if (lm == null || !lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) return;
        oyenteGps = new LocationListener() {
            @Override public void onLocationChanged(Location l) {
                long ahora = System.currentTimeMillis();     // mismo reloj que usa el video
                ultimoPuntoMs = ahora;
                ultimaPrecision = l.hasAccuracy() ? l.getAccuracy() : -1;
                pts.add(new double[]{ahora, l.getLatitude(), l.getLongitude()});
            }
            @Override public void onStatusChanged(String p, int s, Bundle e) { }
            @Override public void onProviderEnabled(String p) { }
            @Override public void onProviderDisabled(String p) { }
        };
        try {
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, oyenteGps, Looper.getMainLooper());
        } catch (SecurityException | IllegalArgumentException e) {
            oyenteGps = null;
        }
    }

    private void detenerGps() {
        if (lm != null && oyenteGps != null) {
            try { lm.removeUpdates(oyenteGps); } catch (Exception ignorada) { }
        }
        oyenteGps = null;
    }

    /* ------------------------------------------------------------------ cámara */

    @Override public void onSurfaceTextureAvailable(SurfaceTexture s, int w, int h) {
        if (tienePermiso(Manifest.permission.CAMERA) && !camaraAbierta && hCam != null) abrirCamara();
    }
    @Override public void onSurfaceTextureSizeChanged(SurfaceTexture s, int w, int h) { }
    @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture s) { return true; }
    @Override public void onSurfaceTextureUpdated(SurfaceTexture s) { }

    private static Size elegirTamano(Size[] lista, int aw, int ah) {
        Size mejor = null;
        for (Size s : lista) {
            if (s.getWidth() > ANCHO_MAX) continue;
            boolean mismaRelacion = aw > 0 && s.getWidth() * ah == s.getHeight() * aw;
            if (aw > 0 && !mismaRelacion) continue;
            if (mejor == null || s.getWidth() * s.getHeight() > mejor.getWidth() * mejor.getHeight()) mejor = s;
        }
        return mejor;
    }

    private void abrirCamara() {
        if (camaraAbierta || terminando) return;
        try {
            CameraManager cm = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            String id = null;
            CameraCharacteristics car = null;
            for (String c : cm.getCameraIdList()) {
                CameraCharacteristics x = cm.getCameraCharacteristics(c);
                Integer lado = x.get(CameraCharacteristics.LENS_FACING);
                if (lado != null && lado == CameraCharacteristics.LENS_FACING_BACK) { id = c; car = x; break; }
            }
            if (id == null) { terminarConError("Este teléfono no tiene cámara trasera."); return; }
            StreamConfigurationMap map = car.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            Integer so = car.get(CameraCharacteristics.SENSOR_ORIENTATION);
            orientSensor = so == null ? 90 : so;
            Size[] vs = map.getOutputSizes(MediaRecorder.class);
            tamVideo = elegirTamano(vs, 16, 9);
            if (tamVideo == null) tamVideo = elegirTamano(vs, 4, 3);
            if (tamVideo == null) tamVideo = elegirTamano(vs, 0, 0);
            if (tamVideo == null) tamVideo = vs[vs.length - 1];
            Size[] ps = map.getOutputSizes(SurfaceTexture.class);
            tamPrev = elegirTamano(ps, tamVideo.getWidth() / gcd(tamVideo.getWidth(), tamVideo.getHeight()),
                    tamVideo.getHeight() / gcd(tamVideo.getWidth(), tamVideo.getHeight()));
            if (tamPrev == null) tamPrev = tamVideo;
            tv.setAspect(tamPrev.getHeight(), tamPrev.getWidth());    // pantalla en vertical
            capa.setAspect(tamPrev.getHeight(), tamPrev.getWidth());

            camaraAbierta = true;
            cm.openCamera(id, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice c) { cam = c; ui.post(RecorridoActivity.this::crearSesion); }
                @Override public void onDisconnected(CameraDevice c) { c.close(); cam = null; camaraAbierta = false; }
                @Override public void onError(CameraDevice c, int e) {
                    c.close(); cam = null; camaraAbierta = false;
                    ui.post(() -> terminarConError("Error de la cámara (código " + e + ")."));
                }
            }, hCam);
        } catch (SecurityException e) {
            terminarConError("Sin permiso de cámara.");
        } catch (Exception e) {
            camaraAbierta = false;
            terminarConError("No se pudo abrir la cámara: " + e.getMessage());
        }
    }

    private static int gcd(int a, int b) { return b == 0 ? a : gcd(b, a % b); }

    private void prepararGrabador() throws Exception {
        archivoVideo = new File(carpeta, "rec_" + System.currentTimeMillis() + ".mp4");
        rec = new MediaRecorder();
        rec.setVideoSource(MediaRecorder.VideoSource.SURFACE);
        rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
        rec.setOutputFile(archivoVideo.getAbsolutePath());
        rec.setVideoEncodingBitRate(BITRATE);
        rec.setVideoFrameRate(30);
        rec.setVideoSize(tamVideo.getWidth(), tamVideo.getHeight());
        rec.setVideoEncoder(MediaRecorder.VideoEncoder.H264);
        rec.setOrientationHint(orientSensor);       // pantalla fija en vertical
        rec.prepare();
    }

    private void crearSesion() {
        if (cam == null || terminando) return;
        try {
            SurfaceTexture st = tv.getSurfaceTexture();
            st.setDefaultBufferSize(tamPrev.getWidth(), tamPrev.getHeight());
            final Surface prev = new Surface(st);
            prepararGrabador();
            final Surface grab = rec.getSurface();
            final CaptureRequest.Builder rb = cam.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
            rb.addTarget(prev);
            rb.addTarget(grab);
            rb.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
            rb.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
            cam.createCaptureSession(Arrays.asList(prev, grab), new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession s) {
                    sesion = s;
                    try { s.setRepeatingRequest(rb.build(), null, hCam); }
                    catch (Exception e) { ui.post(() -> terminarConError("No se pudo iniciar la vista previa.")); return; }
                    ui.post(() -> { btn.setEnabled(true); actualizarInfo(); iniciarVivo(); });
                }
                @Override public void onConfigureFailed(CameraCaptureSession s) {
                    ui.post(() -> terminarConError("No se pudo configurar la cámara para grabar."));
                }
            }, hCam);
        } catch (Exception e) {
            terminarConError("No se pudo preparar la grabación: " + e.getMessage());
        }
    }

    private void cerrarCamara() {
        detenerVivo();
        try { if (sesion != null) sesion.close(); } catch (Exception ignorada) { }
        sesion = null;
        try { if (cam != null) cam.close(); } catch (Exception ignorada) { }
        cam = null;
        camaraAbierta = false;
        if (rec != null) {
            try { rec.release(); } catch (Exception ignorada) { }
            rec = null;
        }
    }

    /* ------------------------------------------------------------------ grabar / detener */

    private void iniciar() {
        if (rec == null || grabando) return;
        try {
            inicioMs = System.currentTimeMillis();
            inicioElapsed = SystemClock.elapsedRealtime();
            rec.start();
            grabando = true;
            btn.setText("■ Detener y analizar");
            actualizarInfo();
            ui.postDelayed(temporizador, 500);
        } catch (Exception e) {
            terminarConError("No se pudo empezar a grabar: " + e.getMessage());
        }
    }

    private final Runnable temporizador = new Runnable() {
        @Override public void run() {
            if (!grabando) return;
            if (SystemClock.elapsedRealtime() - inicioElapsed >= MAX_MS) { detener(); return; }
            actualizarInfo();
            ui.postDelayed(this, 500);
        }
    };

    private void actualizarInfo() {
        String gps;
        long ahora = System.currentTimeMillis();
        if (!tienePermiso(Manifest.permission.ACCESS_FINE_LOCATION)) gps = "GPS: sin permiso (no habrá mapa)";
        else if (oyenteGps == null) gps = "GPS: desactivado en el teléfono (no habrá mapa)";
        else if (ultimoPuntoMs == 0 || ahora - ultimoPuntoMs > 5000) gps = "GPS: buscando señal…";
        else gps = "GPS: ✓ ±" + Math.round(ultimaPrecision) + " m";
        if (grabando) {
            long s = (SystemClock.elapsedRealtime() - inicioElapsed) / 1000;
            info.setText(String.format(Locale.US, "● REC %02d:%02d   (máx. 15 min)\n%s", s / 60, s % 60, gps));
        } else {
            info.setText("Listo. Apunta al camino y pulsa iniciar.\n" + gps);
            ui.postDelayed(() -> { if (!grabando && !terminando) actualizarInfo(); }, 1000);
        }
    }

    private void detener() {
        if (!grabando || terminando) return;
        terminando = true;
        grabando = false;
        ui.removeCallbacks(temporizador);
        final double durS = (SystemClock.elapsedRealtime() - inicioElapsed) / 1000.0;
        boolean ok = true;
        try { if (sesion != null) { sesion.stopRepeating(); sesion.abortCaptures(); } } catch (Exception ignorada) { }
        try { rec.stop(); } catch (RuntimeException e) { ok = false; }   // p. ej. grabación demasiado corta
        try { rec.release(); } catch (Exception ignorada) { }
        rec = null;
        cerrarCamara();
        detenerGps();
        if (!ok || archivoVideo == null || !archivoVideo.isFile() || archivoVideo.length() < 1000) {
            if (archivoVideo != null) //noinspection ResultOfMethodCallIgnored
                archivoVideo.delete();
            Intent r = new Intent().putExtra(EXTRA_ERROR, "La grabación fue demasiado corta o falló. Intenta de nuevo.");
            setResult(RESULT_FIRST_USER, r);
            finish();
            return;
        }
        String nombreGpx = archivoVideo.getName().replace(".mp4", ".gpx");
        int usados = escribirGpx(new File(carpeta, nombreGpx), inicioMs - 10000, inicioMs + (long) (durS * 1000) + 10000);
        Intent r = new Intent()
                .putExtra(EXTRA_VIDEO, archivoVideo.getName())
                .putExtra(EXTRA_GPX, usados >= 2 ? nombreGpx : "")
                .putExtra(EXTRA_INICIO, inicioMs)
                .putExtra(EXTRA_DUR, durS)
                .putExtra(EXTRA_PUNTOS, usados)
                .putExtra(EXTRA_CONTEO, vivoPedido ? conteoJson() : "");
        setResult(RESULT_OK, r);
        finish();
    }

    private int escribirGpx(File f, long desde, long hasta) {
        List<double[]> sel = new ArrayList<>();
        for (double[] p : pts) if (p[0] >= desde && p[0] <= hasta) sel.add(p);
        if (sel.size() < 2) return sel.size();
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        StringBuilder sb = new StringBuilder();
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
          .append("<gpx version=\"1.1\" creator=\"Vialidad\" xmlns=\"http://www.topografix.com/GPX/1/1\"><trk><name>Recorrido</name><trkseg>\n");
        for (double[] p : sel) {
            sb.append(String.format(Locale.US, "<trkpt lat=\"%.7f\" lon=\"%.7f\"><time>%s</time></trkpt>\n",
                    p[1], p[2], fmt.format(new Date((long) p[0]))));
        }
        sb.append("</trkseg></trk></gpx>\n");
        try (FileOutputStream o = new FileOutputStream(f)) {
            o.write(sb.toString().getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return 0;
        }
        return sel.size();
    }

    private void terminarConError(String msg) {
        if (terminando) return;
        terminando = true;
        grabando = false;
        ui.removeCallbacks(temporizador);
        cerrarCamara();
        detenerGps();
        if (archivoVideo != null) //noinspection ResultOfMethodCallIgnored
            archivoVideo.delete();
        setResult(RESULT_FIRST_USER, new Intent().putExtra(EXTRA_ERROR, msg));
        finish();
    }
}
