package com.seraphin.pydrop;

import android.app.Notification;
import android.app.RemoteInput;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.os.Bundle;
import android.os.Parcelable;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Notifications du téléphone sur le PC : WhatsApp, SMS, appels manqués…
 * Android appelle ce service pour chaque notification ; il l'envoie directement aux ordinateurs
 * connectés (même si la page PyDrop dort en arrière-plan) et gère les réponses rapides (RemoteInput).
 */
public class NotifService extends NotificationListenerService {
    static final String PREFS = "pydrop_notif";

    private final ExecutorService pool = Executors.newSingleThreadExecutor();
    private final Map<String, String> icons = new HashMap<>();
    private final Map<String, Long> recent = new HashMap<>();

    public static class ActionAndInput {
        public final Notification.Action action;
        public final RemoteInput remoteInput;
        public final long timestamp;

        public ActionAndInput(Notification.Action action, RemoteInput remoteInput) {
            this.action = action;
            this.remoteInput = remoteInput;
            this.timestamp = System.currentTimeMillis();
        }
    }

    private static final Map<String, ActionAndInput> REPLY_CACHE = new ConcurrentHashMap<>();

    private volatile boolean polling = false;
    private Thread pollThread = null;

    static boolean isEnabled(Context c) {
        return c.getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("enabled", false);
    }

    public static ActionAndInput findReplyAction(Notification n) {
        if (n == null) return null;
        if (n.actions != null) {
            for (Notification.Action a : n.actions) {
                if (a == null || a.actionIntent == null) continue;
                RemoteInput[] inputs = a.getRemoteInputs();
                if (inputs != null) {
                    for (RemoteInput ri : inputs) {
                        if (ri != null && ri.getAllowFreeFormInput()) {
                            return new ActionAndInput(a, ri);
                        }
                    }
                }
            }
        }
        Bundle extras = n.extras;
        if (extras != null) {
            Bundle wearable = extras.getBundle("android.wearable.EXTENSIONS");
            if (wearable != null) {
                ArrayList<Notification.Action> wActions = wearable.getParcelableArrayList("actions");
                if (wActions != null) {
                    for (Notification.Action a : wActions) {
                        if (a == null || a.actionIntent == null) continue;
                        RemoteInput[] inputs = a.getRemoteInputs();
                        if (inputs != null) {
                            for (RemoteInput ri : inputs) {
                                if (ri != null && ri.getAllowFreeFormInput()) {
                                    return new ActionAndInput(a, ri);
                                }
                            }
                        }
                    }
                }
            }
        }
        return null;
    }

    public static boolean replyTo(Context ctx, String notifKey, String text) {
        if (notifKey == null || text == null || text.trim().isEmpty()) return false;
        ActionAndInput ca = REPLY_CACHE.get(notifKey);
        if (ca == null || ca.action == null || ca.remoteInput == null) return false;
        try {
            Intent intent = new Intent();
            Bundle bundle = new Bundle();
            bundle.putCharSequence(ca.remoteInput.getResultKey(), text.trim());
            RemoteInput.addResultsToIntent(new RemoteInput[]{ca.remoteInput}, intent, bundle);
            ca.action.actionIntent.send(ctx, 0, intent);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        startPolling();
    }

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        startPolling();
    }

    @Override
    public void onListenerDisconnected() {
        stopPolling();
        super.onListenerDisconnected();
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
            if (!p.getBoolean("enabled", false)) return;
            String pkg = sbn.getPackageName();
            if (pkg.equals(getPackageName())) return;
            Notification n = sbn.getNotification();
            if ((n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;  // résumé « 3 messages »
            if (sbn.isOngoing()) return;                                    // musique, téléchargements…
            if ((n.flags & Notification.FLAG_ONLY_ALERT_ONCE) != 0 && n.when > 0
                    && System.currentTimeMillis() - n.when > 60000) return;  // mise à jour d'une vieille notification
            Bundle ex = n.extras;
            if (ex == null) return;
            String title = str(ex.getCharSequence(Notification.EXTRA_TITLE));
            String text = str(ex.getCharSequence(Notification.EXTRA_BIG_TEXT));
            if (text.isEmpty()) text = str(ex.getCharSequence(Notification.EXTRA_TEXT));
            // Messageries (WhatsApp, Messages…) : le dernier message reçu, avec son auteur dans un groupe
            Parcelable[] msgs = ex.getParcelableArray(Notification.EXTRA_MESSAGES);
            if (msgs != null && msgs.length > 0 && msgs[msgs.length - 1] instanceof Bundle) {
                Bundle last = (Bundle) msgs[msgs.length - 1];
                String body = str(last.getCharSequence("text"));
                String sender = str(last.getCharSequence("sender"));
                if (!body.isEmpty()) text = !sender.isEmpty() && !sender.equals(title) ? sender + " : " + body : body;
            }
            if (title.isEmpty() && text.isEmpty()) return;

            ActionAndInput replyAction = findReplyAction(n);
            String notifKey = sbn.getKey();
            if (replyAction != null && notifKey != null) {
                REPLY_CACHE.put(notifKey, replyAction);
                long cutoff = System.currentTimeMillis() - 30 * 60 * 1000L;
                REPLY_CACHE.entrySet().removeIf(entry -> entry.getValue().timestamp < cutoff);
            }
            boolean canReply = (replyAction != null);

            String key = pkg + "|" + title + "|" + text;
            long now = System.currentTimeMillis();
            synchronized (recent) {
                Long t = recent.get(key);
                if (t != null && now - t < 8000) return;
                recent.put(key, now);
                if (recent.size() > 200) recent.clear();
            }
            String targets = p.getString("targets", "");
            if (targets.isEmpty()) return;
            final String fTitle = title, fText = text, fNotifKey = notifKey;
            final boolean fCanReply = canReply;
            pool.execute(() -> post(targets, pkg, fTitle, fText, fNotifKey, fCanReply));
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
        if (sbn != null && sbn.getKey() != null) {
            REPLY_CACHE.remove(sbn.getKey());
        }
    }

    private static String str(CharSequence s) {
        return s == null ? "" : s.toString().trim();
    }

    private void post(String targets, String pkg, String title, String text, String notifKey, boolean canReply) {
        try {
            JSONObject t = new JSONObject(targets);
            JSONArray list = t.optJSONArray("list");
            String me = t.optString("me");
            if (list == null || list.length() == 0 || me.isEmpty()) return;
            JSONObject body = new JSONObject();
            body.put("pkg", pkg);
            body.put("app", label(pkg));
            body.put("title", title);
            body.put("text", text);
            body.put("icon", icon(pkg));
            body.put("ts", System.currentTimeMillis());
            if (notifKey != null) body.put("notif_key", notifKey);
            body.put("can_reply", canReply);

            byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
            for (int i = 0; i < list.length(); i++) {
                JSONObject pc = list.getJSONObject(i);
                HttpURLConnection c = null;
                try {
                    String url = pc.getString("base") + "/api/notify?from=" + URLEncoder.encode(me, "UTF-8")
                            + "&token=" + URLEncoder.encode(pc.getString("token"), "UTF-8");
                    c = (HttpURLConnection) new URL(url).openConnection();
                    c.setRequestMethod("POST");
                    c.setDoOutput(true);
                    c.setConnectTimeout(3000);
                    c.setReadTimeout(4000);
                    c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    c.setFixedLengthStreamingMode(data.length);
                    try (OutputStream o = c.getOutputStream()) {
                        o.write(data);
                    }
                    c.getResponseCode();
                } catch (Exception ignored) {
                    // PC éteint ou autre réseau : la notification reste sur le téléphone
                } finally {
                    if (c != null) c.disconnect();
                }
            }
        } catch (Exception ignored) {
        }
    }

    private synchronized void startPolling() {
        if (polling) return;
        polling = true;
        pollThread = new Thread(this::pollLoop, "PyDropNotifPoll");
        pollThread.setDaemon(true);
        pollThread.start();
    }

    private synchronized void stopPolling() {
        polling = false;
        if (pollThread != null) {
            pollThread.interrupt();
            pollThread = null;
        }
    }

    private void pollLoop() {
        while (polling) {
            try {
                SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
                if (!p.getBoolean("enabled", false)) {
                    Thread.sleep(3000);
                    continue;
                }
                String targets = p.getString("targets", "");
                if (targets.isEmpty()) {
                    Thread.sleep(3000);
                    continue;
                }
                JSONObject t = new JSONObject(targets);
                JSONArray list = t.optJSONArray("list");
                String me = t.optString("me");
                if (list == null || list.length() == 0 || me.isEmpty()) {
                    Thread.sleep(3000);
                    continue;
                }
                boolean hadSuccess = false;
                for (int i = 0; i < list.length() && polling; i++) {
                    JSONObject pc = list.getJSONObject(i);
                    String base = pc.getString("base");
                    String token = pc.getString("token");
                    HttpURLConnection c = null;
                    try {
                        String url = base + "/api/notif/poll?from=" + URLEncoder.encode(me, "UTF-8")
                                + "&token=" + URLEncoder.encode(token, "UTF-8");
                        c = (HttpURLConnection) new URL(url).openConnection();
                        c.setRequestMethod("GET");
                        c.setConnectTimeout(4000);
                        c.setReadTimeout(28000);
                        int code = c.getResponseCode();
                        if (code == 200) {
                            hadSuccess = true;
                            ByteArrayOutputStream baos = new ByteArrayOutputStream();
                            byte[] buf = new byte[1024];
                            int r;
                            try (InputStream in = c.getInputStream()) {
                                while ((r = in.read(buf)) != -1) baos.write(buf, 0, r);
                            }
                            JSONObject resp = new JSONObject(baos.toString("UTF-8"));
                            if (resp.has("command")) {
                                handleCommand(resp);
                            }
                        }
                    } catch (Exception ignored) {
                    } finally {
                        if (c != null) c.disconnect();
                    }
                }
                if (!hadSuccess && polling) {
                    Thread.sleep(3000);
                }
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                try { Thread.sleep(3000); } catch (Exception ignored) {}
            }
        }
    }

    private void handleCommand(JSONObject cmd) {
        try {
            String command = cmd.optString("command");
            if ("reply".equals(command)) {
                String key = cmd.optString("key");
                String text = cmd.optString("text");
                replyTo(this, key, text);
            }
        } catch (Exception ignored) {
        }
    }

    private String label(String pkg) {
        try {
            PackageManager pm = getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return pkg;
        }
    }

    private String icon(String pkg) {
        synchronized (icons) {
            if (icons.containsKey(pkg)) return icons.get(pkg);
        }
        String b64 = "";
        try {
            b64 = drawableToPng(getPackageManager().getApplicationIcon(pkg), 96);
        } catch (Exception ignored) {
        }
        synchronized (icons) {
            icons.put(pkg, b64);
        }
        return b64;
    }

    static String drawableToPng(Drawable d, int size) {
        Bitmap bmp;
        if (d instanceof BitmapDrawable && ((BitmapDrawable) d).getBitmap() != null) {
            bmp = Bitmap.createScaledBitmap(((BitmapDrawable) d).getBitmap(), size, size, true);
        } else {
            bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
            Canvas c = new Canvas(bmp);
            d.setBounds(0, 0, size, size);
            d.draw(c);
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        bmp.compress(Bitmap.CompressFormat.PNG, 100, out);
        return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP);
    }

    @Override
    public void onDestroy() {
        stopPolling();
        pool.shutdown();
        super.onDestroy();
    }
}
