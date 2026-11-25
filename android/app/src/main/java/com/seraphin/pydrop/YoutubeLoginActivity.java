package com.seraphin.pydrop;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.webkit.WebSettingsCompat;
import androidx.webkit.WebViewFeature;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

/**
 * Connexion au compte YouTube, pour les vidéos que YouTube réserve aux comptes connectés
 * (« Confirmez que vous n'êtes pas un robot »). Les cookies obtenus sont écrits au format
 * attendu par yt-dlp ; ils ne quittent jamais le téléphone.
 */
public class YoutubeLoginActivity extends Activity {

    static final String COOKIE_FILE = "youtube_cookies.txt";
    // Page de connexion Google (avec retour vers YouTube), et page YouTube mobile en secours
    private static final String LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fm.youtube.com%2F";
    private static final String YOUTUBE_URL = "https://m.youtube.com/";
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorBox;
    private TextView errorText, status;
    private String lastUrl = LOGIN_URL;

    static File cookieFile(Activity a) {
        return new File(a.getFilesDir(), COOKIE_FILE);
    }

    /** Vrai si un compte YouTube est enregistré. */
    static boolean isConnected(Activity a) {
        File f = cookieFile(a);
        if (!f.exists()) return false;
        try {
            String s = new String(java.nio.file.Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
            return s.contains("SAPISID") || s.contains("LOGIN_INFO");
        } catch (Exception e) {
            return false;
        }
    }

    static void logout(Activity a) {
        cookieFile(a).delete();
        CookieManager.getInstance().removeAllCookies(null);
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF070B16);

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(32, 24, 24, 24);
        TextView title = new TextView(this);
        title.setText("Connexion à YouTube");
        title.setTextColor(Color.WHITE);
        title.setTextSize(17);
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button done = new Button(this);
        done.setText("Terminé");
        done.setOnClickListener(v -> finishLogin(true));
        bar.addView(done);
        root.addView(bar);

        // Barre de chargement : la page Google peut être longue à venir sur une connexion mobile
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 10));
        status = new TextView(this);
        status.setTextColor(0xFF8B9AB3);
        status.setTextSize(13);
        status.setPadding(32, 10, 32, 10);
        status.setText("Chargement de la page de connexion…");
        root.addView(status);

        FrameLayout stack = new FrameLayout(this);
        web = new WebView(this);
        web.setBackgroundColor(Color.WHITE);
        stack.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // Message d'erreur avec « Réessayer » (au lieu de la page d'erreur brute)
        errorBox = new LinearLayout(this);
        errorBox.setOrientation(LinearLayout.VERTICAL);
        errorBox.setGravity(Gravity.CENTER);
        errorBox.setPadding(64, 64, 64, 64);
        errorBox.setBackgroundColor(0xFF070B16);
        errorText = new TextView(this);
        errorText.setTextColor(Color.WHITE);
        errorText.setTextSize(16);
        errorText.setGravity(Gravity.CENTER);
        errorBox.addView(errorText);
        Button retry = new Button(this);
        retry.setText("Réessayer");
        retry.setOnClickListener(v -> load(lastUrl));
        errorBox.addView(retry);
        Button alt = new Button(this);
        alt.setText("Passer par YouTube");
        alt.setOnClickListener(v -> load(YOUTUBE_URL));
        errorBox.addView(alt);
        errorBox.setVisibility(View.GONE);
        stack.addView(errorBox, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(stack, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(web, true);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        // Google refuse la connexion depuis une « WebView » : on se présente comme Chrome mobile
        s.setUserAgentString(s.getUserAgentString().replace("; wv", "").replaceAll("Version/[0-9.]+ ", ""));
        if (WebViewFeature.isFeatureSupported(WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST)) {
            WebSettingsCompat.setRequestedWithHeaderOriginAllowList(s, Collections.emptySet());
        }
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int p) {
                progress.setProgress(p);
                progress.setVisibility(p >= 100 ? View.INVISIBLE : View.VISIBLE);
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                if (errorBox.getVisibility() != View.VISIBLE) {
                    status.setText(url != null && url.contains("youtube.com")
                            ? "Sur YouTube : touchez l'icône de compte puis « Se connecter »."
                            : "Connectez-vous avec votre compte Google.");
                }
                // De retour sur YouTube avec un compte : c'est fini
                if (url != null && url.contains("youtube.com") && hasAccount()) finishLogin(false);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (!request.isForMainFrame()) return;
                String reason = String.valueOf(error.getDescription());
                errorText.setText(reason.contains("TIMED_OUT") || reason.contains("TIMEOUT")
                        ? "La page de connexion met trop de temps à venir.\nVérifiez la connexion Internet, puis réessayez.\n"
                        : "Impossible d'ouvrir la page de connexion.\n(" + reason + ")\n");
                errorBox.setVisibility(View.VISIBLE);
                status.setText("Pas de connexion à Google");
            }
        });
        load(LOGIN_URL);
    }

    private void load(String url) {
        lastUrl = url;
        errorBox.setVisibility(View.GONE);
        status.setText("Chargement…");
        progress.setProgress(0);
        progress.setVisibility(View.VISIBLE);
        web.loadUrl(url);
    }

    private boolean hasAccount() {
        String c = CookieManager.getInstance().getCookie("https://www.youtube.com");
        return c != null && (c.contains("SAPISID") || c.contains("LOGIN_INFO"));
    }

    private boolean finished;

    private void finishLogin(boolean byUser) {
        if (finished) return;
        CookieManager.getInstance().flush();
        if (!hasAccount()) {
            if (byUser) {
                Toast.makeText(this, "Pas encore connecté à YouTube", Toast.LENGTH_SHORT).show();
                setResult(RESULT_CANCELED);
                finished = true;
                finish();
            }
            return;
        }
        finished = true;
        try {
            writeCookies();
            Toast.makeText(this, "Compte YouTube enregistré dans PyDrop", Toast.LENGTH_SHORT).show();
            setResult(RESULT_OK);
        } catch (Exception e) {
            Toast.makeText(this, "Enregistrement impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
            setResult(RESULT_CANCELED);
        }
        finish();
    }

    /** Écrit les cookies YouTube au format « Netscape » utilisé par yt-dlp. */
    private void writeCookies() throws Exception {
        StringBuilder out = new StringBuilder("# Netscape HTTP Cookie File\n");
        long expiry = System.currentTimeMillis() / 1000 + 180L * 24 * 3600;
        String[][] sites = {{"https://www.youtube.com", ".youtube.com"}, {"https://accounts.google.com", ".google.com"}};
        for (String[] site : sites) {
            String all = CookieManager.getInstance().getCookie(site[0]);
            if (all == null) continue;
            for (String part : all.split(";")) {
                int eq = part.indexOf('=');
                if (eq <= 0) continue;
                String name = part.substring(0, eq).trim(), value = part.substring(eq + 1).trim();
                out.append(site[1]).append("\tTRUE\t/\tTRUE\t").append(expiry).append('\t')
                        .append(name).append('\t').append(value).append('\n');
            }
        }
        try (FileOutputStream o = new FileOutputStream(cookieFile(this))) {
            o.write(out.toString().getBytes(StandardCharsets.UTF_8));
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else finishLogin(true);
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
