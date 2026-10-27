package ec.vialidad.app;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.OutputStream;
import java.net.URLEncoder;

/**
 * Cascarón mínimo: muestra la página móvil (/m/) del servidor que corre en el PC.
 * Todo el análisis se hace en el PC; la app solo captura fotos/videos, los envía y guarda informes.
 */
public class MainActivity extends Activity {

    private static final int REQ_ARCHIVO = 1001;
    private static final String PREFS = "vialidad";

    private SharedPreferences prefs;
    private FrameLayout raiz;
    private WebView web;
    private View pantallaConfig;

    private ValueCallback<Uri[]> callbackArchivo;
    private Uri uriCaptura;       // destino de la foto/video grabado con la cámara
    private View vistaCompleta;   // video a pantalla completa
    private WebChromeClient.CustomViewCallback callbackCompleta;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        raiz = new FrameLayout(this);
        setContentView(raiz);
        crearWebView();
        if (prefs.getString("servidor", "").isEmpty()) {
            mostrarConfig();
        } else {
            abrirServidor();
        }
    }

    /* ---------------------------------------------------------------- WebView */

    private void crearWebView() {
        web = new WebView(this);
        web.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.addJavascriptInterface(new Puente(), "Android");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) mostrarError(String.valueOf(err.getDescription()));
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                String srv = prefs.getString("servidor", "");
                if (u.toString().startsWith(srv)) return false;
                if (u.getScheme() != null && u.getScheme().startsWith("http")) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignorada) { }
                    return true;
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView v, String url, Bitmap f) { }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (callbackArchivo != null) callbackArchivo.onReceiveValue(null);
                callbackArchivo = cb;
                try {
                    startActivityForResult(crearIntentArchivo(p), REQ_ARCHIVO);
                } catch (Exception e) {
                    callbackArchivo = null;
                    cb.onReceiveValue(null);
                    Toast.makeText(MainActivity.this, "No se pudo abrir la cámara o la galería", Toast.LENGTH_LONG).show();
                    return false;
                }
                return true;
            }

            @Override
            public void onShowCustomView(View vista, CustomViewCallback cb) {
                if (vistaCompleta != null) { cb.onCustomViewHidden(); return; }
                vistaCompleta = vista;
                callbackCompleta = cb;
                vista.setBackgroundColor(Color.BLACK);
                raiz.addView(vista, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            }

            @Override
            public void onHideCustomView() {
                if (vistaCompleta == null) return;
                raiz.removeView(vistaCompleta);
                vistaCompleta = null;
                if (callbackCompleta != null) callbackCompleta.onCustomViewHidden();
                callbackCompleta = null;
            }
        });

        // Descargas normales (p. ej. el video marcado): se hacen con el administrador de descargas.
        web.setDownloadListener((url, ua, contentDisposition, mime, length) -> {
            try {
                String nombre = URLUtil.guessFileName(url, contentDisposition, mime);
                DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
                String cookie = CookieManager.getInstance().getCookie(url);
                if (cookie != null) r.addRequestHeader("Cookie", cookie);
                if (mime != null && !mime.isEmpty()) r.setMimeType(mime);
                r.setTitle(nombre);
                r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nombre);
                ((DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
                Toast.makeText(this, "Descargando " + nombre + " en Descargas", Toast.LENGTH_LONG).show();
            } catch (Exception e) {
                Toast.makeText(this, "No se pudo descargar: " + e.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
        raiz.addView(web);
    }

    /** Cámara (foto/video) cuando la página pide «capture»; galería/archivos en caso contrario. */
    private Intent crearIntentArchivo(WebChromeClient.FileChooserParams p) throws Exception {
        uriCaptura = null;
        String acepta = "";
        String[] tipos = p.getAcceptTypes();
        if (tipos != null && tipos.length > 0 && tipos[0] != null) acepta = tipos[0];
        if (p.isCaptureEnabled()) {
            ContentValues cv = new ContentValues();
            String marca = String.valueOf(System.currentTimeMillis());
            Intent cam;
            if (acepta.startsWith("video")) {
                cv.put(MediaStore.Video.Media.DISPLAY_NAME, "vialidad_" + marca + ".mp4");
                cv.put(MediaStore.Video.Media.MIME_TYPE, "video/mp4");
                cv.put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/Vialidad");
                uriCaptura = getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, cv);
                cam = new Intent(MediaStore.ACTION_VIDEO_CAPTURE);
            } else {
                cv.put(MediaStore.Images.Media.DISPLAY_NAME, "vialidad_" + marca + ".jpg");
                cv.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                cv.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Vialidad");
                uriCaptura = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cv);
                cam = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            }
            if (uriCaptura != null) {
                cam.putExtra(MediaStore.EXTRA_OUTPUT, uriCaptura);
                cam.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                return cam;
            }
        }
        return p.createIntent();
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req != REQ_ARCHIVO) { super.onActivityResult(req, res, data); return; }
        ValueCallback<Uri[]> cb = callbackArchivo;
        callbackArchivo = null;
        Uri[] resultado = null;
        if (res == RESULT_OK) {
            if (uriCaptura != null) {
                resultado = new Uri[]{uriCaptura};
            } else {
                resultado = WebChromeClient.FileChooserParams.parseResult(res, data);
            }
        } else if (uriCaptura != null) {
            try { getContentResolver().delete(uriCaptura, null, null); } catch (Exception ignorada) { }
        }
        uriCaptura = null;
        if (cb != null) cb.onReceiveValue(resultado);
    }

    /* ---------------------------------------------------------------- servidor */

    private String normalizar(String s) {
        s = s == null ? "" : s.trim();
        if (s.isEmpty()) return "";
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://" + s;


        // Nuevo bloque para limpiar cualquier ruta y conservar únicamente el protocolo, IP y puerto
        Uri u = Uri.parse(s); 
        if (u.getScheme() == null || u.getAuthority() == null) return s; 
        return u.getScheme() + "://" + u.getAuthority();
    }

    private void abrirServidor() {
        String srv = prefs.getString("servidor", "");
        String token = prefs.getString("clave", "");
        String url = token.isEmpty() ? srv + "/m/" : srv + "/acceso?t=" + safeEncode(token);
        if (pantallaConfig != null) { raiz.removeView(pantallaConfig); pantallaConfig = null; }
        web.setVisibility(View.VISIBLE);
        web.loadUrl(url);
    }

    private static String safeEncode(String s) {
        try { return URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return s; }
    }

    private TextView texto(String t, int sp, boolean negrita, int color) {
        TextView v = new TextView(this);
        v.setText(t);
        v.setTextSize(sp);
        v.setTextColor(color);
        if (negrita) v.setTypeface(Typeface.DEFAULT_BOLD);
        return v;
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    private void mostrarConfig() {
        if (pantallaConfig != null) raiz.removeView(pantallaConfig);
        web.setVisibility(View.GONE);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.parseColor("#F1F5F9"));
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(24), dp(48), dp(24), dp(24));
        sv.addView(col);

        col.addView(texto("Vialidad", 28, true, Color.parseColor("#0F172A")));
        col.addView(texto("Conecta la app con el servidor que corre en tu PC (mismo wifi).", 15, false, Color.parseColor("#475569")));

        TextView l1 = texto("Dirección del servidor", 14, true, Color.parseColor("#0F172A"));
        l1.setPadding(0, dp(24), 0, dp(4));
        col.addView(l1);
        final EditText dir = new EditText(this);
        dir.setHint("http://192.168.1.10:8000");
        dir.setSingleLine(true);
        dir.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        dir.setText(prefs.getString("servidor", ""));
        col.addView(dir);

        TextView l2 = texto("Clave de acceso (solo si configuraste APP_TOKEN)", 14, true, Color.parseColor("#0F172A"));
        l2.setPadding(0, dp(16), 0, dp(4));
        col.addView(l2);
        final EditText clave = new EditText(this);
        clave.setHint("opcional");
        clave.setSingleLine(true);
        clave.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        clave.setText(prefs.getString("clave", ""));
        col.addView(clave);

        Button ir = new Button(this);
        ir.setText("Guardar y abrir");
        ir.setAllCaps(false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52));
        lp.topMargin = dp(24);
        ir.setLayoutParams(lp);
        ir.setOnClickListener(v -> {
            String s = normalizar(dir.getText().toString());
            if (s.isEmpty()) { dir.setError("Escribe la dirección, por ejemplo http://192.168.1.10:8000"); return; }
            prefs.edit().putString("servidor", s).putString("clave", clave.getText().toString().trim()).apply();
            abrirServidor();
        });
        col.addView(ir);

        TextView ayuda = texto("En el PC, abre una consola y escribe ipconfig: la «Dirección IPv4» es la que va aquí, seguida de :8000. "
                + "El servidor debe estar encendido con --host 0.0.0.0.", 13, false, Color.parseColor("#64748B"));
        ayuda.setPadding(0, dp(20), 0, 0);
        col.addView(ayuda);

        pantallaConfig = sv;
        raiz.addView(sv, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    private void mostrarError(String detalle) {
        String srv = prefs.getString("servidor", "");
        String h = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                + "<body style='font-family:sans-serif;padding:28px;color:#0f172a;background:#f1f5f9'>"
                + "<h2>No se pudo conectar</h2>"
                + "<p>Servidor: <b>" + TextUtilsHtml(srv) + "</b></p>"
                + "<p style='color:#64748b'>Revisa que el PC esté encendido, que el servidor esté corriendo, "
                + "que el teléfono esté en el mismo wifi y que el firewall de Windows permita la conexión.</p>"
                + "<p style='color:#94a3b8;font-size:13px'>" + TextUtilsHtml(detalle) + "</p>"
                + "<p><button style='font-size:17px;padding:14px 22px;border:0;border-radius:10px;background:#f59e0b;font-weight:700' onclick='Android.reintentar()'>Reintentar</button></p>"
                + "<p><button style='font-size:15px;padding:12px 20px;border:0;border-radius:10px;background:#e2e8f0' onclick='Android.changeServer()'>Cambiar servidor</button></p>"
                + "</body></html>";
        web.loadDataWithBaseURL(null, h, "text/html", "UTF-8", null);
    }

    private static String TextUtilsHtml(String s) {
        return s == null ? "" : s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    /* ---------------------------------------------------------------- puente JS */

    private class Puente {
        /** Guarda un archivo (p. ej. el informe PDF) en la carpeta Descargas del teléfono. */
        @JavascriptInterface
        public void saveFile(String nombre, String mime, String base64) {
            try {
                byte[] datos = Base64.decode(base64, Base64.DEFAULT);
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, nombre);
                cv.put(MediaStore.Downloads.MIME_TYPE, mime);
                cv.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                cv.put(MediaStore.Downloads.IS_PENDING, 1);
                Uri u = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (u == null) throw new Exception("no se pudo crear el archivo");
                try (OutputStream o = getContentResolver().openOutputStream(u)) {
                    o.write(datos);
                }
                cv.clear();
                cv.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(u, cv, null, null);
                aviso("Guardado en Descargas: " + nombre);
            } catch (Exception e) {
                aviso("No se pudo guardar: " + e.getMessage());
            }
        }

        @JavascriptInterface
        public void changeServer() { runOnUiThread(MainActivity.this::mostrarConfig); }

        @JavascriptInterface
        public void reintentar() { runOnUiThread(MainActivity.this::abrirServidor); }
    }

    private void aviso(String m) {
        runOnUiThread(() -> Toast.makeText(this, m, Toast.LENGTH_LONG).show());
    }

    /* ---------------------------------------------------------------- ciclo de vida */

    @Override
    public void onBackPressed() {
        if (vistaCompleta != null) {
            if (callbackCompleta != null) callbackCompleta.onCustomViewHidden();
            raiz.removeView(vistaCompleta);
            vistaCompleta = null;
            return;
        }
        if (pantallaConfig != null && !prefs.getString("servidor", "").isEmpty()) {
            abrirServidor();
            return;
        }
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() { web.onPause(); super.onPause(); }

    @Override
    protected void onResume() { super.onResume(); web.onResume(); }
}
