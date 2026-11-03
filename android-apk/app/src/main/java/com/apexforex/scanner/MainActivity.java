package com.apexforex.scanner;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.graphics.Color;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://apex-forex-scanner.vercel.app/";
    private WebView webView;
    private ProgressBar progress;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(8,10,13));
        getWindow().setNavigationBarColor(Color.rgb(8,10,13));
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(8,10,13));
        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String host = request.getUrl().getHost();
                if (host != null && (host.equals("apex-forex-scanner.vercel.app") || host.endsWith(".vercel.app"))) return false;
                return false;
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) {
                progress.setProgress(value);
                progress.setVisibility(value >= 100 ? View.GONE : View.VISIBLE);
            }
        });
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(Color.rgb(218,169,40)));
        root.addView(webView, new FrameLayout.LayoutParams(-1,-1));
        FrameLayout.LayoutParams bar = new FrameLayout.LayoutParams(-1, 4);
        root.addView(progress, bar);
        setContentView(root);
        if (state == null) webView.loadUrl(APP_URL);
        else webView.restoreState(state);
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (webView != null) webView.saveState(out);
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (webView != null) { webView.destroy(); webView = null; }
        super.onDestroy();
    }
}
