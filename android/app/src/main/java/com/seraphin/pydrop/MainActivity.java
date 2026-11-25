package com.seraphin.pydrop;

import android.Manifest;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.IntentFilter;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.ResolveInfo;
import android.view.KeyEvent;
import java.util.Collections;
import java.util.HashSet;
import java.util.zip.Deflater;
import java.util.zip.ZipOutputStream;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import android.content.ContentValues;
import android.content.SharedPreferences;
import com.yausername.ffmpeg.FFmpeg;
import com.yausername.youtubedl_android.YoutubeDL;
import com.yausername.youtubedl_android.YoutubeDLRequest;
import kotlin.Unit;
import android.provider.Settings;
import java.security.MessageDigest;
import android.database.Cursor;
import android.provider.OpenableColumns;
import org.json.JSONArray;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import android.media.MediaScannerConnection;
import android.provider.MediaStore;
import android.webkit.MimeTypeMap;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;

/**
 * PyDrop Android : la page mobile tourne dans une WebView, et l'application
 * ajoute ce qu'un navigateur ne sait pas faire : écouter les annonces UDP des
 * ordinateurs PyDrop (découverte automatique) et enregistrer les fichiers reçus.
 */
public class MainActivity extends Activity {

    private static final int DISCOVERY_PORT = 47474;
    private static final int REQ_FILES = 10;
    private static final int REQ_CAMERA = 11;
    private static final int REQ_STORAGE = 12;
    private static final int REQ_YOUTUBE = 13;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingPermission;
    private Thread discoveryThread;
    private volatile boolean discovering;
    private WifiManager.MulticastLock multicastLock;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        IntentFilter installFilter = new IntentFilter(INSTALL_ACTION);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(installReceiver, installFilter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(installReceiver, installFilter);

        web = new WebView(this);
        web.setBackgroundColor(0xFF070B16);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowFileAccessFromFileURLs(true);
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        web.addJavascriptInterface(new Bridge(), "PyDropNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("file".equals(uri.getScheme())) return false;
                // Les fichiers à télécharger passent par le gestionnaire de téléchargements
                if (uri.getPath() != null && uri.getPath().startsWith("/api/dl/")) {
                    enqueueDownload(uri.toString(), null);
                    return true;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) {
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                try {
                    startActivityForResult(Intent.createChooser(i, "Choisir des fichiers"), REQ_FILES);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> {
                    if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(request.getResources());
                    } else {
                        pendingPermission = request;
                        requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA);
                    }
                });
            }
        });
        web.setDownloadListener((url, ua, disposition, mime, length) ->
                enqueueDownload(url, URLUtil.guessFileName(url, disposition, mime)));

        if (Build.VERSION.SDK_INT < 29
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
        }

        handleShareIntent(getIntent());
        web.loadUrl("file:///android_asset/www/index.html");
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleShareIntent(intent);
        js("window.pydropCheckShare && window.pydropCheckShare()");
    }

    // ------------------------------------------------------------------ partage Android

    private final List<JSONObject> pendingShares = new ArrayList<>();
    private final Map<String, Uri> sharedUris = new ConcurrentHashMap<>();
    private final Set<String> uploadCancelled = ConcurrentHashMap.newKeySet();
    private final Map<String, HttpURLConnection> uploadConns = new ConcurrentHashMap<>();

    private void handleShareIntent(Intent intent) {
        if (intent == null || intent.getAction() == null) return;
        String action = intent.getAction();
        if (Intent.ACTION_SEND.equals(action)) {
            Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (uri != null) {
                addShared(uri);
            } else {
                CharSequence text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
                if (text != null) {
                    java.util.regex.Matcher m = java.util.regex.Pattern.compile("https?://\\S+").matcher(text);
                    if (m.find()) addSharedLink(m.group());  // un lien (YouTube…) : le PC téléchargera la vidéo
                    else addSharedText(text.toString());
                }
            }
        } else if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            ArrayList<Uri> uris = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (uris != null) for (Uri u : uris) addShared(u);
        }
        // Ne pas retraiter ce partage si l'activité est recréée
        intent.setAction(null);
    }

    private void addSharedLink(String url) {
        try {
            JSONObject o = new JSONObject();
            o.put("key", UUID.randomUUID().toString().replace("-", ""));
            o.put("kind", "link");
            o.put("url", url);
            o.put("name", url);
            o.put("size", 0);
            synchronized (pendingShares) {
                pendingShares.add(o);
            }
        } catch (Exception ignored) {
        }
    }

    private void addSharedText(String text) {
        try {
            File f = new File(getCacheDir(), "partage-" + System.currentTimeMillis() + ".txt");
            try (FileOutputStream o = new FileOutputStream(f)) {
                o.write(text.getBytes(StandardCharsets.UTF_8));
            }
            addShared(Uri.fromFile(f));
        } catch (Exception e) {
            Toast.makeText(this, "Partage impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void addShared(Uri uri) {
        String name = null;
        long size = -1;
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int n = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                int s = c.getColumnIndex(OpenableColumns.SIZE);
                if (n >= 0) name = c.getString(n);
                if (s >= 0 && !c.isNull(s)) size = c.getLong(s);
            }
        } catch (Exception ignored) {
        }
        if ("file".equals(uri.getScheme()) && uri.getPath() != null) {
            File f = new File(uri.getPath());
            name = f.getName();
            size = f.length();
        }
        if (name == null) name = uri.getLastPathSegment() == null ? "fichier" : uri.getLastPathSegment();
        try {
            String key = UUID.randomUUID().toString().replace("-", "");
            sharedUris.put(key, uri);
            JSONObject o = new JSONObject();
            o.put("key", key);
            o.put("name", name);
            o.put("size", size);
            synchronized (pendingShares) {
                pendingShares.add(o);
            }
        } catch (Exception ignored) {
        }
    }

    private void uploadSharedBlocking(String key, String tid, String url, long offset, long size) {
        String qid = JSONObject.quote(tid);
        Uri uri = sharedUris.get(key);
        uploadCancelled.remove(tid);
        HttpURLConnection c = null;
        try {
            if (uri == null) throw new SecurityException("fichier partagé indisponible");
            try (InputStream in = getContentResolver().openInputStream(uri)) {
                if (in == null) throw new SecurityException("fichier illisible");
                long left = offset;
                while (left > 0) {
                    long n = in.skip(left);
                    if (n <= 0) {
                        if (in.read() < 0) throw new SecurityException("fichier modifié");
                        n = 1;
                    }
                    left -= n;
                }
                c = (HttpURLConnection) new URL(url).openConnection();
                uploadConns.put(tid, c);
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setConnectTimeout(8000);
                c.setRequestProperty("Content-Type", "application/octet-stream");
                if (size >= 0) c.setFixedLengthStreamingMode(size - offset);
                else c.setChunkedStreamingMode(256 * 1024);
                long done = offset, last = 0;
                try (OutputStream o = c.getOutputStream()) {
                    byte[] buf = new byte[256 * 1024];
                    int r;
                    while ((r = in.read(buf)) != -1) {
                        if (uploadCancelled.contains(tid)) return;
                        o.write(buf, 0, r);
                        done += r;
                        long now = System.currentTimeMillis();
                        if (now - last > 200) {
                            last = now;
                            js("window.onNativeUploadProgress && window.onNativeUploadProgress(" + qid + "," + done + ")");
                        }
                    }
                }
                int code = c.getResponseCode();
                // (on garde le fichier : il peut partir aussi vers un autre ordinateur)
                js("window.onNativeUploadDone && window.onNativeUploadDone(" + qid + "," + code + ")");
            }
        } catch (SecurityException | java.io.FileNotFoundException e) {
            js("window.onNativeUploadDone && window.onNativeUploadDone(" + qid + ",-3)");
        } catch (Exception e) {
            js("window.onNativeUploadDone && window.onNativeUploadDone(" + qid + ",-1)");
        } finally {
            uploadConns.remove(tid);
            if (c != null) c.disconnect();
        }
    }

    /** Dossier reçu : on déplie l'archive dans Téléchargements/PyDrop/<dossier>. */
    private void unpackZip(Partial p, String folder) throws Exception {
        folder = folder.replaceAll("[\\\\/:*?\"<>|]", "_");
        byte[] buf = new byte[256 * 1024];
        try (InputStream raw = p.uri != null ? getContentResolver().openInputStream(p.uri) : new FileInputStream(p.file);
             ZipInputStream z = new ZipInputStream(raw)) {
            ZipEntry e;
            while ((e = z.getNextEntry()) != null) {
                String rel = e.getName().replace('\\', '/');
                if (rel.startsWith("/") || ("/" + rel + "/").contains("/../")) continue;
                if (e.isDirectory()) {
                    if (Build.VERSION.SDK_INT < 29) {
                        new File(new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "PyDrop/" + folder), rel).mkdirs();
                    }
                    continue;
                }
                int slash = rel.lastIndexOf('/');
                String sub = slash >= 0 ? rel.substring(0, slash) : "";
                String base = rel.substring(slash + 1);
                OutputStream out;
                Uri item = null;
                if (Build.VERSION.SDK_INT >= 29) {
                    String ext = MimeTypeMap.getFileExtensionFromUrl(Uri.encode(base));
                    String mime = ext == null ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.Downloads.DISPLAY_NAME, base);
                    v.put(MediaStore.Downloads.MIME_TYPE, mime == null ? "application/octet-stream" : mime);
                    v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/PyDrop/" + folder + (sub.isEmpty() ? "" : "/" + sub));
                    v.put(MediaStore.Downloads.IS_PENDING, 1);
                    item = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                    if (item == null) throw new Exception("stockage indisponible");
                    out = getContentResolver().openOutputStream(item);
                } else {
                    File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "PyDrop/" + folder + "/" + sub);
                    dir.mkdirs();
                    out = new FileOutputStream(new File(dir, base));
                }
                try (OutputStream o = out) {
                    int r;
                    while ((r = z.read(buf)) != -1) o.write(buf, 0, r);
                }
                if (item != null) {
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.Downloads.IS_PENDING, 0);
                    getContentResolver().update(item, v, null, null);
                }
            }
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        startDiscovery();
        // L'application revient au premier plan : la page vérifie et rétablit ses connexions
        if (web != null) js("window.pydropResume && window.pydropResume()");
        if (pendingInstall != null && Build.VERSION.SDK_INT >= 26 && getPackageManager().canRequestPackageInstalls()) {
            Uri uri = pendingInstall;
            pendingInstall = null;
            openUri(uri);  // APK simple ou paquet .apks
        }
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(installReceiver);
        } catch (Exception ignored) {
        }
        stopDiscovery();
        if (web != null) web.destroy();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        // La page ferme d'abord ses fenêtres ouvertes ; sinon on quitte
        web.evaluateJavascript("window.pydropBack ? window.pydropBack() : false", value -> {
            if (!"true".equals(value)) MainActivity.super.onBackPressed();
        });
    }

    // ------------------------------------------------------------------ fichiers

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_YOUTUBE) {
            js("window.onYoutubeAccount && window.onYoutubeAccount(" + YoutubeLoginActivity.isConnected(this) + ")");
            return;
        }
        if (requestCode != REQ_FILES || fileCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK && data != null) {
            ClipData clip = data.getClipData();
            if (clip != null) {
                result = new Uri[clip.getItemCount()];
                for (int i = 0; i < clip.getItemCount(); i++) result[i] = clip.getItemAt(i).getUri();
            } else if (data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
        }
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_CAMERA && pendingPermission != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermission.grant(pendingPermission.getResources());
            } else {
                pendingPermission.deny();
            }
            pendingPermission = null;
        }
    }

    private void enqueueDownload(String url, String name) {
        try {
            if (name == null || name.isEmpty()) name = URLUtil.guessFileName(url, null, null);
            name = name.replaceAll("[\\\\/:*?\"<>|]", "_");
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            r.setTitle(name);
            r.setDescription("Reçu avec PyDrop");
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "PyDrop/" + name);
            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            dm.enqueue(r);
            Toast.makeText(this, "Enregistrement dans Téléchargements/PyDrop", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "Téléchargement impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    // ------------------------------------------------------------------ découverte

    private void startDiscovery() {
        if (discovering) return;
        discovering = true;
        WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        if (wifi != null) {
            multicastLock = wifi.createMulticastLock("pydrop");
            multicastLock.setReferenceCounted(false);
            multicastLock.acquire();
        }
        discoveryThread = new Thread(() -> {
            while (discovering) {
                try (DatagramSocket sock = new DatagramSocket(null)) {
                    sock.setReuseAddress(true);
                    sock.setBroadcast(true);
                    sock.bind(new InetSocketAddress(DISCOVERY_PORT));
                    sock.setSoTimeout(1000);
                    byte[] buf = new byte[4096];
                    while (discovering) {
                        DatagramPacket p = new DatagramPacket(buf, buf.length);
                        try {
                            sock.receive(p);
                        } catch (SocketTimeoutException e) {
                            continue;
                        }
                        handleAnnounce(new String(p.getData(), 0, p.getLength(), StandardCharsets.UTF_8),
                                p.getAddress().getHostAddress());
                    }
                } catch (Exception e) {
                    try {
                        Thread.sleep(2000);
                    } catch (InterruptedException ie) {
                        return;
                    }
                }
            }
        }, "pydrop-discovery");
        discoveryThread.start();
    }

    private void stopDiscovery() {
        discovering = false;
        if (discoveryThread != null) discoveryThread.interrupt();
        if (multicastLock != null && multicastLock.isHeld()) multicastLock.release();
    }

    private void handleAnnounce(String text, String ip) {
        try {
            JSONObject o = new JSONObject(text);
            if (!"pydrop".equals(o.optString("app")) || !"desktop".equals(o.optString("type"))) return;
            o.put("ip", ip);
            final String js = "window.onNativePeer && window.onNativePeer(" + o + ")";
            runOnUiThread(() -> web.evaluateJavascript(js, null));
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------------ pont JS

    private class Bridge {
        @JavascriptInterface
        public String deviceName() {
            String maker = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER;
            String model = Build.MODEL == null ? "Android" : Build.MODEL;
            if (!maker.isEmpty() && !model.toLowerCase().startsWith(maker.toLowerCase())) {
                model = Character.toUpperCase(maker.charAt(0)) + maker.substring(1) + " " + model;
            }
            return model;
        }

        @JavascriptInterface
        public void download(String url, String name) {
            runOnUiThread(() -> enqueueDownload(url, name));
        }

        /** Téléchargement fait par l'application elle-même, avec progression envoyée à la page. */
        @JavascriptInterface
        public void fetchFile(String id, String url, String name, String unpack, String shaUrl) {
            new Thread(() -> fetchFileBlocking(id, url, name, unpack, shaUrl), "pydrop-dl").start();
        }

        /** Fichiers reçus via « Partager avec PyDrop », en attente du choix de l'appareil. */
        @JavascriptInterface
        public String takeShared() {
            JSONArray out = new JSONArray();
            synchronized (pendingShares) {
                for (JSONObject o : pendingShares) out.put(o);
                pendingShares.clear();
            }
            return out.toString();
        }

        @JavascriptInterface
        public void uploadShared(String key, String tid, String url, String offset, String size) {
            new Thread(() -> uploadSharedBlocking(key, tid, url, Long.parseLong(offset), Long.parseLong(size)), "pydrop-up").start();
        }

        /** Vidéo par lien téléchargée par le téléphone lui-même (yt-dlp embarqué), sans ordinateur. */
        @JavascriptInterface
        public void videoDownload(String id, String url, String mode) {
            new Thread(() -> videoBlocking(id, url, mode), "pydrop-video").start();
        }

        /** Options pour les développeurs (ou « À propos » si elles ne sont pas encore activées). */
        @JavascriptInterface
        public void openDevSettings() {
            runOnUiThread(() -> {
                boolean enabled = Settings.Global.getInt(getContentResolver(), Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) == 1;
                Intent i = new Intent(enabled ? Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS : Settings.ACTION_DEVICE_INFO_SETTINGS);
                if (!enabled) Toast.makeText(MainActivity.this, "Touchez 7 fois « Numéro de build »", Toast.LENGTH_LONG).show();
                try {
                    startActivity(i);
                } catch (ActivityNotFoundException e) {
                    startActivity(new Intent(Settings.ACTION_SETTINGS));
                }
            });
        }

        @JavascriptInterface
        public boolean youtubeConnected() {
            return YoutubeLoginActivity.isConnected(MainActivity.this);
        }

        @JavascriptInterface
        public void youtubeLogin() {
            runOnUiThread(() -> startActivityForResult(new Intent(MainActivity.this, YoutubeLoginActivity.class), REQ_YOUTUBE));
        }

        @JavascriptInterface
        public void youtubeLogout() {
            runOnUiThread(() -> {
                YoutubeLoginActivity.logout(MainActivity.this);
                js("window.onYoutubeAccount && window.onYoutubeAccount(false)");
            });
        }

        @JavascriptInterface
        public void videoCancel(String id) {
            videoCancelled.add(id);
            new Thread(() -> YoutubeDL.getInstance().destroyProcessById(id)).start();
        }

        @JavascriptInterface
        public void cancelUpload(String tid) {
            uploadCancelled.add(tid);
            HttpURLConnection c = uploadConns.get(tid);
            if (c != null) new Thread(c::disconnect).start();
        }

        @JavascriptInterface
        public void cancelFile(String id) {
            cancelDownload(id);
        }

        @JavascriptInterface
        public void openFile(String id, String saved) {
            runOnUiThread(() -> {
                Uri uri = savedFiles.get(id);
                if (uri == null && saved != null && !saved.isEmpty()) uri = Uri.parse(saved);
                if (uri == null) {
                    openDownloadsApp();
                    return;
                }
                openUri(uri);
            });
        }

        @JavascriptInterface
        public void openDownloads() {
            runOnUiThread(MainActivity.this::openDownloadsApp);
        }

        // ---- presse-papiers partagé
        @JavascriptInterface
        public void setClipboard(String text) {
            runOnUiThread(() -> {
                try {
                    ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                    cm.setPrimaryClip(ClipData.newPlainText("PyDrop", text));
                } catch (Exception ignored) {
                }
            });
        }

        @JavascriptInterface
        public String getClipboard() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                ClipData d = cm.getPrimaryClip();
                if (d == null || d.getItemCount() == 0) return "";
                CharSequence t = d.getItemAt(0).coerceToText(MainActivity.this);
                return t == null ? "" : t.toString();
            } catch (Exception e) {
                return "";
            }
        }

        // ---- notifications sur le PC
        @JavascriptInterface
        public boolean notifSupported() {
            // Absent de l'édition standard (Play Protect bloque les applis qui lisent les notifications)
            try {
                getPackageManager().getServiceInfo(new ComponentName(MainActivity.this, NotifService.class), 0);
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        @JavascriptInterface
        public boolean notifAccess() {
            String flat = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
            return flat != null && flat.contains(getPackageName() + "/");
        }

        @JavascriptInterface
        public boolean notifEnabled() {
            return NotifService.isEnabled(MainActivity.this);
        }

        @JavascriptInterface
        public void setNotifEnabled(boolean on) {
            getSharedPreferences(NotifService.PREFS, MODE_PRIVATE).edit().putBoolean("enabled", on).apply();
        }

        @JavascriptInterface
        public void setNotifTargets(String json) {
            getSharedPreferences(NotifService.PREFS, MODE_PRIVATE).edit().putString("targets", json).apply();
        }

        @JavascriptInterface
        public boolean replyNotif(String key, String text) {
            return NotifService.replyTo(MainActivity.this, key, text);
        }

        @JavascriptInterface
        public void openNotifAccess() {
            runOnUiThread(() -> {
                try {
                    if (Build.VERSION.SDK_INT >= 30) {
                        Intent i = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS);
                        i.putExtra(Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME,
                                new ComponentName(MainActivity.this, NotifService.class).flattenToString());
                        startActivity(i);
                        return;
                    }
                } catch (Exception ignored) {
                }
                try {
                    startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
                } catch (Exception e) {
                    startActivity(new Intent(Settings.ACTION_SETTINGS));
                }
            });
        }

        @JavascriptInterface
        public void openAppInfo() {
            runOnUiThread(() -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + getPackageName()))));
        }

        // ---- télécommande : les boutons de volume passent les diapositives
        @JavascriptInterface
        public void setVolumeKeys(boolean on) {
            volumeKeys = on;
        }

        // ---- envoyer une application installée
        @JavascriptInterface
        public void listApps() {
            new Thread(MainActivity.this::listAppsBlocking).start();
        }

        @JavascriptInterface
        public void shareApps(String json) {
            new Thread(() -> shareAppsBlocking(json)).start();
        }
    }

    // ------------------------------------------------------------------ boutons de volume

    private volatile boolean volumeKeys;

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        int code = event.getKeyCode();
        if (volumeKeys && (code == KeyEvent.KEYCODE_VOLUME_UP || code == KeyEvent.KEYCODE_VOLUME_DOWN)) {
            if (event.getAction() == KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0) {
                js("window.onVolumeKey && window.onVolumeKey('" + (code == KeyEvent.KEYCODE_VOLUME_UP ? "up" : "down") + "')");
            }
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    // ------------------------------------------------------------------ applications installées

    private void listAppsBlocking() {
        JSONArray arr = new JSONArray();
        try {
            PackageManager pm = getPackageManager();
            Intent main = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
            List<ResolveInfo> found = pm.queryIntentActivities(main, 0);
            Set<String> seen = new HashSet<>();
            List<JSONObject> apps = new ArrayList<>();
            for (ResolveInfo ri : found) {
                ApplicationInfo ai = ri.activityInfo.applicationInfo;
                if (!seen.add(ai.packageName)) continue;
                boolean system = (ai.flags & ApplicationInfo.FLAG_SYSTEM) != 0
                        && (ai.flags & ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) == 0;
                if (system) continue;  // applis du constructeur : déjà présentes sur les autres téléphones
                JSONObject o = new JSONObject();
                o.put("pkg", ai.packageName);
                o.put("label", ai.loadLabel(pm).toString());
                String version = "";
                try {
                    PackageInfo pi = pm.getPackageInfo(ai.packageName, 0);
                    version = pi.versionName == null ? "" : pi.versionName;
                } catch (Exception ignored) {
                }
                o.put("version", version);
                long size = new File(ai.sourceDir).length();
                boolean split = ai.splitSourceDirs != null && ai.splitSourceDirs.length > 0;
                if (split) for (String sp : ai.splitSourceDirs) size += new File(sp).length();
                o.put("size", size);
                o.put("split", split);
                try {
                    o.put("icon", NotifService.drawableToPng(ai.loadIcon(pm), 72));
                } catch (Exception e) {
                    o.put("icon", "");
                }
                apps.add(o);
            }
            Collections.sort(apps, (a, b) -> a.optString("label").compareToIgnoreCase(b.optString("label")));
            for (JSONObject o : apps) arr.put(o);
        } catch (Exception ignored) {
        }
        js("window.onApps && window.onApps(" + JSONObject.quote(arr.toString()) + ")");
    }

    private static String safeFileName(String s) {
        String r = s.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return r.isEmpty() ? "application" : r;
    }

    /** Prépare chaque application en fichier installable puis ouvre le choix des ordinateurs. */
    private void shareAppsBlocking(String json) {
        int added = 0;
        try {
            JSONArray pkgs = new JSONArray(json);
            PackageManager pm = getPackageManager();
            File dir = new File(getCacheDir(), "apps");
            dir.mkdirs();
            for (int i = 0; i < pkgs.length(); i++) {
                String pkg = pkgs.getString(i);
                try {
                    ApplicationInfo ai = pm.getApplicationInfo(pkg, 0);
                    PackageInfo pi = pm.getPackageInfo(pkg, 0);
                    String name = safeFileName(ai.loadLabel(pm).toString()
                            + (pi.versionName != null ? " " + pi.versionName : ""));
                    if (ai.splitSourceDirs == null || ai.splitSourceDirs.length == 0) {
                        // Une seule pièce : l'APK lui-même, installable partout
                        addSharedFile(new File(ai.sourceDir), name + ".apk");
                    } else {
                        // Application en plusieurs morceaux (Play Store) : un paquet .apks que PyDrop sait installer
                        File out = new File(dir, name + ".apks");
                        try (ZipOutputStream zip = new ZipOutputStream(new FileOutputStream(out))) {
                            zip.setLevel(Deflater.NO_COMPRESSION);
                            List<String> parts = new ArrayList<>();
                            parts.add(ai.sourceDir);
                            Collections.addAll(parts, ai.splitSourceDirs);
                            byte[] buf = new byte[256 * 1024];
                            for (String part : parts) {
                                File f = new File(part);
                                zip.putNextEntry(new ZipEntry(f.getName()));
                                try (InputStream in = new FileInputStream(f)) {
                                    int r;
                                    while ((r = in.read(buf)) != -1) zip.write(buf, 0, r);
                                }
                                zip.closeEntry();
                            }
                        }
                        addSharedFile(out, out.getName());
                    }
                    added++;
                } catch (Exception e) {
                    final String msg = pkg + " : " + e.getMessage();
                    runOnUiThread(() -> Toast.makeText(this, "Application illisible — " + msg, Toast.LENGTH_LONG).show());
                }
            }
        } catch (Exception ignored) {
        }
        if (added > 0) js("window.pydropCheckShare && window.pydropCheckShare()");
        else js("window.onAppsShared && window.onAppsShared(false)");
    }

    private void addSharedFile(File f, String name) throws Exception {
        String key = UUID.randomUUID().toString().replace("-", "");
        sharedUris.put(key, Uri.fromFile(f));
        JSONObject o = new JSONObject();
        o.put("key", key);
        o.put("name", name);
        o.put("size", f.length());
        synchronized (pendingShares) {
            pendingShares.add(o);
        }
    }

    // ------------------------------------------------------------------ installation des paquets .apks

    private static final String INSTALL_ACTION = "com.seraphin.pydrop.INSTALL_RESULT";

    private final BroadcastReceiver installReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    try {
                        startActivity(confirm);
                    } catch (Exception ignored) {
                    }
                }
            } else if (status == PackageInstaller.STATUS_SUCCESS) {
                Toast.makeText(MainActivity.this, "Application installée", Toast.LENGTH_LONG).show();
            } else if (status != PackageInstaller.STATUS_FAILURE_ABORTED) {
                String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                Toast.makeText(MainActivity.this, "Installation impossible" + (msg != null ? " : " + msg : ""),
                        Toast.LENGTH_LONG).show();
            }
        }
    };

    private String displayName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst() && !c.isNull(0)) return c.getString(0);
        } catch (Exception ignored) {
        }
        String last = uri.getLastPathSegment();
        return last == null ? "" : last;
    }

    private void installBundle(Uri uri) {
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            pendingInstall = uri;
            Toast.makeText(this, "Autorisez PyDrop à installer cette application, puis revenez", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
            return;
        }
        Toast.makeText(this, "Préparation de l'installation…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            PackageInstaller installer = getPackageManager().getPackageInstaller();
            int sid = -1;
            try {
                PackageInstaller.SessionParams params =
                        new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                sid = installer.createSession(params);
                int count = 0;
                try (PackageInstaller.Session session = installer.openSession(sid)) {
                    try (ZipInputStream zin = new ZipInputStream(getContentResolver().openInputStream(uri))) {
                        ZipEntry e;
                        byte[] buf = new byte[256 * 1024];
                        while ((e = zin.getNextEntry()) != null) {
                            String nm = e.getName();
                            if (e.isDirectory() || !nm.toLowerCase().endsWith(".apk")) continue;
                            try (OutputStream out = session.openWrite((count++) + "_" + new File(nm).getName(), 0, e.getSize())) {
                                int r;
                                while ((r = zin.read(buf)) != -1) out.write(buf, 0, r);
                                session.fsync(out);
                            }
                        }
                    }
                    if (count == 0) throw new Exception("aucune application dans ce fichier");
                    Intent cb = new Intent(INSTALL_ACTION).setPackage(getPackageName());
                    int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    PendingIntent pending = PendingIntent.getBroadcast(MainActivity.this, sid, cb, flags);
                    session.commit(pending.getIntentSender());
                }
            } catch (Exception ex) {
                if (sid >= 0) {
                    try {
                        installer.abandonSession(sid);
                    } catch (Exception ignored) {
                    }
                }
                final String msg = ex.getMessage() == null ? "erreur" : ex.getMessage();
                runOnUiThread(() -> Toast.makeText(this, "Installation impossible : " + msg, Toast.LENGTH_LONG).show());
            }
        }).start();
    }

    private Uri pendingInstall;

    private void openUri(Uri uri) {
        String shown = displayName(uri).toLowerCase();
        if (shown.endsWith(".apks") || shown.endsWith(".xapk") || shown.endsWith(".apkm")) {
            installBundle(uri);
            return;
        }
        String type = null;
        try {
            type = getContentResolver().getType(uri);
        } catch (Exception ignored) {
        }
        boolean isApk = "application/vnd.android.package-archive".equals(type);
        // Un APK : Android demande d'abord d'autoriser PyDrop à installer des applications
        if (isApk && Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            pendingInstall = uri;
            Toast.makeText(this, "Autorisez PyDrop à installer cette application, puis revenez", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
            return;
        }
        Intent i = new Intent(Intent.ACTION_VIEW);
        i.setDataAndType(uri, type);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            startActivity(i);
        } catch (Exception e) {
            openDownloadsApp();
        }
    }

    private String sha256Of(Partial p) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[1024 * 1024];
        try (InputStream in = p.uri != null ? getContentResolver().openInputStream(p.uri) : new FileInputStream(p.file)) {
            int r;
            while ((r = in.read(buf)) != -1) md.update(buf, 0, r);
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : md.digest()) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    /** Empreinte du fichier sur le PC. null si le PC ne sait pas la donner : on ne bloque pas pour autant. */
    private String remoteSha(String shaUrl) {
        if (shaUrl == null || shaUrl.isEmpty()) return null;
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(shaUrl).openConnection();
            c.setConnectTimeout(8000);
            c.setReadTimeout(600000);
            if (c.getResponseCode() != 200) return null;
            StringBuilder sb = new StringBuilder();
            try (InputStream in = c.getInputStream()) {
                byte[] buf = new byte[1024];
                int r;
                while ((r = in.read(buf)) != -1) sb.append(new String(buf, 0, r, StandardCharsets.UTF_8));
            }
            return new JSONObject(sb.toString()).optString("sha256", null);
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    // ------------------------------------------------------------------ vidéos par lien

    private boolean videoReady;
    private final Set<String> videoCancelled = ConcurrentHashMap.newKeySet();

    private synchronized void ensureVideoTools(String qid) throws Exception {
        if (!videoReady) {
            js("window.onVideoProgress && window.onVideoProgress(" + qid + ",-1,0,'Préparation (première fois)…')");
            YoutubeDL.getInstance().init(getApplication());
            FFmpeg.getInstance().init(getApplication());
            videoReady = true;
        }
        // YouTube change souvent : yt-dlp se met à jour une fois par jour
        SharedPreferences prefs = getSharedPreferences("pydrop", MODE_PRIVATE);
        long now = System.currentTimeMillis();
        if (now - prefs.getLong("ytdlpUpdate", 0) > 24L * 3600 * 1000) {
            js("window.onVideoProgress && window.onVideoProgress(" + qid + ",-1,0,'Mise à jour du téléchargeur…')");
            try {
                YoutubeDL.getInstance().updateYoutubeDL(getApplication(), YoutubeDL.UpdateChannel._STABLE);
            } catch (Exception ignored) {
            }
            prefs.edit().putLong("ytdlpUpdate", now).apply();
        }
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        f.delete();
    }

    private void videoBlocking(String id, String url, String mode) {
        String qid = JSONObject.quote(id);
        File dir = new File(getCacheDir(), "video/" + id.replaceAll("[^A-Za-z0-9]", ""));
        videoCancelled.remove(id);
        try {
            deleteTree(dir);
            dir.mkdirs();
            ensureVideoTools(qid);
            if (videoCancelled.contains(id)) throw new YoutubeDL.CanceledException();
            YoutubeDLRequest r = new YoutubeDLRequest(url);
            r.addOption("--no-playlist");
            r.addOption("--no-mtime");
            r.addOption("-o", dir.getAbsolutePath() + "/%(title).120B.%(ext)s");
            // Compte YouTube enregistré dans PyDrop : évite la « vérification anti-robot »
            File cookies = YoutubeLoginActivity.cookieFile(this);
            if (url.matches("(?i).*(youtube\\.com|youtu\\.be).*") && YoutubeLoginActivity.isConnected(this)) {
                r.addOption("--cookies", cookies.getAbsolutePath());
            }
            if ("audio".equals(mode)) {
                r.addOption("-f", "ba[ext=m4a]/ba/b");
            } else {
                r.addOption("-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b");
                r.addOption("--merge-output-format", "mp4");
            }
            js("window.onVideoProgress && window.onVideoProgress(" + qid + ",0,0,'Téléchargement…')");
            final long[] last = {0};
            YoutubeDL.getInstance().execute(r, id, (progress, eta, line) -> {
                long t = System.currentTimeMillis();
                if (t - last[0] > 300) {
                    last[0] = t;
                    js("window.onVideoProgress && window.onVideoProgress(" + qid + "," + progress + "," + eta + ",'Téléchargement…')");
                }
                return Unit.INSTANCE;
            });
            if (videoCancelled.contains(id)) throw new YoutubeDL.CanceledException();

            // Le fichier final : le plus gros du dossier (les morceaux temporaires ont été fusionnés)
            File out = null;
            File[] files = dir.listFiles();
            if (files != null) for (File f : files) {
                String n = f.getName();
                if (f.isFile() && !n.endsWith(".part") && !n.endsWith(".ytdl") && (out == null || f.length() > out.length())) out = f;
            }
            if (out == null) throw new IllegalStateException("aucun fichier téléchargé");

            js("window.onVideoProgress && window.onVideoProgress(" + qid + ",100,0,'Enregistrement…')");
            Partial p = createPartial(out.getName());
            byte[] buf = new byte[1024 * 1024];
            try (InputStream in = new FileInputStream(out); OutputStream o = openPartial(p, false)) {
                int n;
                while ((n = in.read(buf)) != -1) o.write(buf, 0, n);
            }
            String uri = "";
            if (p.uri != null) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(p.uri, v, null, null);
                savedFiles.put(id, p.uri);
                uri = p.uri.toString();
            } else {
                MediaScannerConnection.scanFile(this, new String[]{p.file.getAbsolutePath()}, null, null);
            }
            js("window.onVideoDone && window.onVideoDone(" + qid + ",true,''," + JSONObject.quote(uri) + ","
                    + JSONObject.quote(out.getName()) + "," + out.length() + ")");
        } catch (YoutubeDL.CanceledException e) {
            js("window.onVideoDone && window.onVideoDone(" + qid + ",false,'annulé','','',0)");
        } catch (Throwable e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            if (msg.length() > 600) msg = msg.substring(msg.length() - 600);  // la fin contient l'erreur utile
            js("window.onVideoDone && window.onVideoDone(" + qid + ",false," + JSONObject.quote(msg) + ",'','',0)");
        } finally {
            deleteTree(dir);
        }
    }

    private void openDownloadsApp() {
        try {
            startActivity(new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS));
        } catch (ActivityNotFoundException ignored) {
        }
    }

    // ------------------------------------------------------------------ téléchargement intégré

    private final Map<String, Uri> savedFiles = new ConcurrentHashMap<>();
    /** Fichiers en cours ou interrompus : on garde la partie reçue pour reprendre. */
    private final Map<String, Partial> partials = new ConcurrentHashMap<>();
    private final Set<String> running = ConcurrentHashMap.newKeySet();
    private final Set<String> cancelled = ConcurrentHashMap.newKeySet();

    private static class Partial {
        Uri uri;
        File file;
        long done;
    }

    private static class CancelledDownload extends Exception {
    }

    private void cancelDownload(String id) {
        cancelled.add(id);
        if (!running.contains(id)) deletePartial(id);
    }

    private void deletePartial(String id) {
        Partial p = partials.remove(id);
        if (p == null) return;
        if (p.uri != null) {
            try {
                getContentResolver().delete(p.uri, null, null);
            } catch (Exception ignored) {
            }
        }
        if (p.file != null) p.file.delete();
    }

    private Partial createPartial(String name) throws Exception {
        Partial p = new Partial();
        String ext = MimeTypeMap.getFileExtensionFromUrl(Uri.encode(name));
        String mime = ext == null ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
        if (mime == null) mime = "application/octet-stream";
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues v = new ContentValues();
            v.put(MediaStore.Downloads.DISPLAY_NAME, name);
            v.put(MediaStore.Downloads.MIME_TYPE, mime);
            v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/PyDrop");
            v.put(MediaStore.Downloads.IS_PENDING, 1);
            p.uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (p.uri == null) throw new Exception("stockage indisponible");
        } else {
            File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "PyDrop");
            dir.mkdirs();
            File f = new File(dir, name);
            int n = 1;
            String base = name.contains(".") ? name.substring(0, name.lastIndexOf('.')) : name;
            String suffix = name.contains(".") ? name.substring(name.lastIndexOf('.')) : "";
            while (f.exists()) f = new File(dir, base + " (" + (n++) + ")" + suffix);
            p.file = f;
        }
        return p;
    }

    private OutputStream openPartial(Partial p, boolean append) throws Exception {
        if (p.uri != null) return getContentResolver().openOutputStream(p.uri, append ? "wa" : "wt");
        return new FileOutputStream(p.file, append);
    }

    private void fetchFileBlocking(String id, String url, String name, String unpack, String shaUrl) {
        if (!running.add(id)) return;  // déjà en cours
        cancelled.remove(id);
        name = name.replaceAll("[\\/:*?\"<>|]", "_");
        HttpURLConnection c = null;
        String qid = JSONObject.quote(id);
        try {
            Partial p = partials.get(id);
            if (p == null) {
                p = createPartial(name);
                partials.put(id, p);
            }
            c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(8000);
            c.setReadTimeout(30000);
            if (p.done > 0) c.setRequestProperty("Range", "bytes=" + p.done + "-");
            int code = c.getResponseCode();
            long total;
            boolean append;
            if (code == 206) {
                append = true;
                String cr = c.getHeaderField("Content-Range");  // bytes 100-999/1000
                total = cr != null && cr.contains("/") ? Long.parseLong(cr.substring(cr.lastIndexOf('/') + 1).trim()) : -1;
            } else if (code == 200) {
                append = false;
                p.done = 0;
                total = c.getContentLengthLong();
            } else if (code == 416) {
                append = true;  // tout était déjà reçu
                total = p.done;
            } else {
                throw new IllegalStateException(code == 410 ? "annulé par le PC"
                        : code == 403 || code == 404 ? "fichier plus disponible" : "le PC a répondu " + code);
            }

            long last = 0;
            if (code != 416) {
                try (InputStream in = c.getInputStream(); OutputStream o = openPartial(p, append)) {
                    byte[] buf = new byte[256 * 1024];
                    int r;
                    while ((r = in.read(buf)) != -1) {
                        if (cancelled.contains(id)) throw new CancelledDownload();
                        o.write(buf, 0, r);
                        p.done += r;
                        long now = System.currentTimeMillis();
                        if (now - last > 200) {
                            last = now;
                            js("window.onNativeProgress && window.onNativeProgress(" + qid + "," + p.done + "," + total + ")");
                        }
                    }
                }
            }
            if (total > 0 && p.done < total) throw new java.io.IOException("connexion coupée");

            // Le fichier reçu est-il identique à celui du PC ?
            js("window.onNativeVerify && window.onNativeVerify(" + qid + ")");
            String expected = remoteSha(shaUrl);
            if (expected != null && !expected.equalsIgnoreCase(sha256Of(p))) {
                throw new IllegalStateException("le fichier reçu est abîmé, réessayez");
            }

            if (p.uri != null) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(p.uri, v, null, null);
                savedFiles.put(id, p.uri);
                js("window.onNativeSaved && window.onNativeSaved(" + qid + "," + JSONObject.quote(p.uri.toString()) + ")");
            } else {
                MediaScannerConnection.scanFile(this, new String[]{p.file.getAbsolutePath()}, null, null);
            }
            partials.remove(id);
            String note = "";
            if (unpack != null && !unpack.isEmpty()) {
                js("window.onNativeUnpack && window.onNativeUnpack(" + qid + ")");
                try {
                    unpackZip(p, unpack);
                    if (p.uri != null) getContentResolver().delete(p.uri, null, null);
                    else p.file.delete();
                    savedFiles.remove(id);
                } catch (Exception e) {
                    note = "unzip_failed";  // l'archive reste dans Téléchargements/PyDrop
                }
            }
            js("window.onNativeDone && window.onNativeDone(" + qid + ",true," + JSONObject.quote(note) + ",false)");
        } catch (CancelledDownload e) {
            deletePartial(id);
            js("window.onNativeDone && window.onNativeDone(" + qid + ",false,'annulé',false)");
        } catch (java.io.IOException e) {
            String msg = e.getMessage() == null ? "connexion coupée" : e.getMessage();
            if (msg.contains("ENOSPC") || msg.contains("No space")) {
                deletePartial(id);
                js("window.onNativeDone && window.onNativeDone(" + qid + ",false,'espace insuffisant sur le téléphone',false)");
                return;
            }
            // Coupure réseau : on garde la partie reçue, la page relancera la reprise
            if (cancelled.contains(id)) deletePartial(id);
            js("window.onNativeDone && window.onNativeDone(" + qid + ",false," + JSONObject.quote(msg) + ",true)");
        } catch (Exception e) {
            deletePartial(id);
            String msg = e.getMessage() == null ? "erreur" : e.getMessage();
            js("window.onNativeDone && window.onNativeDone(" + qid + ",false," + JSONObject.quote(msg) + ",false)");
        } finally {
            if (c != null) c.disconnect();
            running.remove(id);
            if (cancelled.contains(id)) deletePartial(id);
        }
    }

    private void js(String code) {
        runOnUiThread(() -> web.evaluateJavascript(code, null));
    }
}
