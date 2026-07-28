package dev.andra.runtime;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.List;

/**
 * Plugin detail: metadata, enable toggle, hooks list, raw files.
 */
public final class PluginDetailActivity extends Activity {
    public static final String EXTRA_PLUGIN_DIR = "plugin_dir";

    private File pluginDir;
    private PluginModels.Plugin plugin;
    private TextView statusChip;
    private TextView metaBody;
    private LinearLayout hooksBox;
    private TextView filesBody;
    private TextView logBody;

    public static void open(Context ctx, File dir) {
        Intent i = new Intent(ctx, PluginDetailActivity.class);
        i.putExtra(EXTRA_PLUGIN_DIR, dir.getAbsolutePath());
        ctx.startActivity(i);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (plugin != null) {
            bind();
            refreshLogs();
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 23) {
            getWindow().setStatusBarColor(0xFF0B1220);
            getWindow().setNavigationBarColor(0xFF0B1220);
        }

        String path = getIntent() != null ? getIntent().getStringExtra(EXTRA_PLUGIN_DIR) : null;
        if (path == null || path.isEmpty()) {
            Toast.makeText(this, "缺少插件路径", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }
        // normalize trailing slash
        while (path.endsWith("/") && path.length() > 1) {
            path = path.substring(0, path.length() - 1);
        }
        pluginDir = new File(path);
        plugin = PluginModels.loadOne(pluginDir);

        float d = getResources().getDisplayMetrics().density;
        int pad = dp(16, d);

        // Always show a page — even if plugin.json unreadable (permission / missing).
        if (plugin == null) {
            setContentView(errorPage(d, pad, path));
            return;
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF0B1220);

        // top bar
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(pad, pad + dp(6, d), pad, pad);
        top.setBackgroundResource(R.drawable.bg_header);

        TextView back = new TextView(this);
        back.setText("← 返回");
        back.setTextColor(0xFF00C9A7);
        back.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        back.setTypeface(Typeface.DEFAULT_BOLD);
        back.setPadding(0, dp(8, d), dp(12, d), dp(8, d));
        back.setOnClickListener(v -> finish());
        top.addView(back);

        LinearLayout titleCol = new LinearLayout(this);
        titleCol.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams tLp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        top.addView(titleCol, tLp);

        TextView title = new TextView(this);
        title.setText(plugin.name);
        title.setTextColor(0xFFE8EEF7);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        titleCol.addView(title);

        TextView sub = new TextView(this);
        sub.setText("插件详情");
        sub.setTextColor(0xFF8B9BB4);
        sub.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        titleCol.addView(sub);

        statusChip = chip(d,
                plugin.enabled ? getString(R.string.badge_on) : getString(R.string.badge_off),
                plugin.enabled ? 0xFF00C9A7 : 0xFFFF6B7A,
                plugin.enabled ? R.drawable.bg_chip_on : R.drawable.bg_chip_off);
        top.addView(statusChip);
        root.addView(top);

        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(pad, pad, pad, pad + dp(28, d));
        scroll.addView(content);

        // actions
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setWeightSum(2f);

        Button toggle = primaryButton(d, plugin.enabled ? "禁用插件" : "启用插件");
        toggle.setOnClickListener(v -> toggleEnabled(toggle));
        actions.addView(toggle, weightLp(d, true));

        Button copy = ghostButton(d, "复制路径");
        copy.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null) {
                cm.setPrimaryClip(ClipData.newPlainText("plugin-dir", pluginDir.getAbsolutePath()));
                Toast.makeText(this, "已复制路径", Toast.LENGTH_SHORT).show();
            }
        });
        actions.addView(copy, weightLp(d, false));
        content.addView(actions);

        Button openHost = ghostButton(d, "打开宿主 App");
        openHost.setOnClickListener(v -> openHostApp());
        LinearLayout.LayoutParams openLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        openLp.topMargin = dp(10, d);
        content.addView(openHost, openLp);

        // meta
        content.addView(section(d, "基本信息"), sectionLp(d));
        metaBody = cardText(d);
        content.addView(wrapCard(d, metaBody), cardLp());

        // logs (primary need)
        content.addView(section(d, "运行日志"), sectionLp(d));
        LinearLayout logActions = new LinearLayout(this);
        logActions.setOrientation(LinearLayout.HORIZONTAL);
        logActions.setWeightSum(3f);
        Button refreshLog = primaryButton(d, "刷新日志");
        refreshLog.setOnClickListener(v -> refreshLogs());
        logActions.addView(refreshLog, weight3(d, 0));
        Button copyLog = ghostButton(d, "复制");
        copyLog.setOnClickListener(v -> {
            CharSequence t = logBody != null ? logBody.getText() : "";
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null) {
                cm.setPrimaryClip(ClipData.newPlainText("andra-log", t));
                Toast.makeText(this, "日志已复制", Toast.LENGTH_SHORT).show();
            }
        });
        logActions.addView(copyLog, weight3(d, 1));
        Button clearLog = ghostButton(d, "清空");
        clearLog.setOnClickListener(v -> {
            String host = plugin != null ? plugin.targetPackage : null;
            AndraLog.clearFiles(host);
            AndraLog.i(plugin != null ? plugin.name : null, "日志已清空");
            refreshLogs();
            Toast.makeText(this, "已清空文件日志", Toast.LENGTH_SHORT).show();
        });
        logActions.addView(clearLog, weight3(d, 2));
        content.addView(logActions);

        TextView logHint = new TextView(this);
        logHint.setText("仅显示信息与错误。打开宿主触发后点刷新。");
        logHint.setTextColor(0xFF5C6B82);
        logHint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        logHint.setPadding(0, dp(8, d), 0, dp(6, d));
        content.addView(logHint);

        logBody = cardText(d);
        logBody.setTypeface(Typeface.MONOSPACE);
        logBody.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        logBody.setTextColor(0xFFB8C4D6);
        // keep log card reasonably tall but scrollable with page
        content.addView(wrapCard(d, logBody), cardLp());

        // hooks
        content.addView(section(d, "Hooks（" + plugin.hooks.size() + "）"), sectionLp(d));
        hooksBox = new LinearLayout(this);
        hooksBox.setOrientation(LinearLayout.VERTICAL);
        hooksBox.setBackgroundResource(R.drawable.bg_card);
        hooksBox.setPadding(pad, pad, pad, pad);
        content.addView(hooksBox, cardLp());

        // files
        content.addView(section(d, "目录文件"), sectionLp(d));
        filesBody = cardText(d);
        filesBody.setTypeface(Typeface.MONOSPACE);
        filesBody.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        content.addView(wrapCard(d, filesBody), cardLp());

        // tip
        content.addView(section(d, "说明"), sectionLp(d));
        TextView tip = cardText(d);
        tip.setText("启用/禁用只影响本机 .enabled 标记。\n"
                + "改完后请强停宿主 App 再打开，LSPosed 才会重新加载 hooks。\n"
                + "作用域：LSPosed → Andra → 只勾宿主包名，不要勾系统框架。");
        tip.setTextColor(0xFF8B9BB4);
        tip.setLineSpacing(dp(2, d), 1f);
        content.addView(wrapCard(d, tip), cardLp());

        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);
        bind();
        refreshLogs();
    }

    private void refreshLogs() {
        if (logBody == null) return;
        logBody.setText("加载中…");
        final String name = plugin != null ? plugin.name : null;
        final String host = plugin != null ? plugin.targetPackage : null;
        final File privDir = new File(getExternalFilesDir(null), "logs");
        new Thread(() -> {
            // Host media log is often mode 660 — UI process cannot read it.
            // Always try su copy into Andra private files first.
            String pullNote = tryPullHostLog(host, privDir);
            final String text = AndraLog.readRecent(name, host, 80, true);
            final String shown;
            if (text != null && !text.startsWith("（暂无") && !text.isEmpty()) {
                shown = text;
            } else {
                shown = text + (pullNote == null || pullNote.isEmpty() ? "" : "\n\n" + pullNote);
            }
            runOnUiThread(() -> {
                if (logBody != null) logBody.setText(shown);
            });
        }, "andra-log-refresh").start();
    }

    /**
     * Copy host-owned andra.log into app-private dir (readable by this UI).
     * Uses {@code su -c} because media files are typically u0_aXXX:media_rw 660.
     */
    private String tryPullHostLog(String host, File privDir) {
        if (host == null || host.isEmpty()) return "";
        //noinspection ResultOfMethodCallIgnored
        privDir.mkdirs();
        File priv = new File(privDir, "andra.log");
        File src = new File(android.os.Environment.getExternalStorageDirectory(),
                "Android/media/" + host + "/Andra/logs/andra.log");
        File pub = new File(android.os.Environment.getExternalStorageDirectory(),
                "Andra/logs/andra.log");

        // Fast path: already readable
        try {
            if (src.isFile() && src.canRead()) {
                copyFile(src, priv);
                tryCopy(src, pub);
                return "";
            }
            if (pub.isFile() && pub.canRead()) {
                copyFile(pub, priv);
                return "";
            }
        } catch (Throwable ignored) {
        }

        // su copy — KernelSU needs a single -c argument
        String srcPath = src.getAbsolutePath();
        String privPath = priv.getAbsolutePath();
        String pubPath = pub.getAbsolutePath();
        String cmd = "mkdir -p '" + privDir.getAbsolutePath() + "' '/sdcard/Andra/logs' "
                + "&& if [ -f '" + srcPath + "' ]; then "
                + "cp -f '" + srcPath + "' '" + privPath + "' "
                + "&& cp -f '" + srcPath + "' '" + pubPath + "' "
                + "&& chmod 666 '" + privPath + "' '" + pubPath + "' 2>/dev/null; "
                + "echo OK; else echo NOFILE; fi";
        String result = runSu(cmd);
        if (result != null && result.contains("OK") && priv.isFile()) {
            return "";
        }
        // last try: cat via su into private file
        String catCmd = "mkdir -p '" + privDir.getAbsolutePath() + "' "
                + "&& cat '" + srcPath + "' > '" + privPath + "' 2>/dev/null "
                + "&& chmod 666 '" + privPath + "' 2>/dev/null "
                + "&& test -s '" + privPath + "' && echo OK || echo FAIL";
        result = runSu(catCmd);
        if (result != null && result.contains("OK") && priv.isFile() && priv.length() > 0) {
            return "";
        }
        return "拉取宿主日志失败（权限）。可在电脑执行：\n"
                + "adb shell su -c 'cp "
                + srcPath + " "
                + privPath + "'";
    }

    private static String runSu(String cmd) {
        Process p = null;
        try {
            p = Runtime.getRuntime().exec(new String[]{"su", "-c", cmd});
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            java.io.InputStream in = p.getInputStream();
            byte[] buf = new byte[1024];
            int n;
            // also drain briefly
            long deadline = System.currentTimeMillis() + 4000;
            while (System.currentTimeMillis() < deadline) {
                if (in.available() > 0) {
                    n = in.read(buf);
                    if (n > 0) bos.write(buf, 0, n);
                } else if (!p.isAlive()) {
                    while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
                    break;
                } else {
                    Thread.sleep(30);
                }
            }
            try {
                p.waitFor(2, java.util.concurrent.TimeUnit.SECONDS);
            } catch (Throwable ignored) {
            }
            return bos.toString("UTF-8");
        } catch (Throwable t) {
            return null;
        } finally {
            if (p != null) p.destroy();
        }
    }

    private static void tryCopy(File src, File dst) {
        try {
            File parent = dst.getParentFile();
            if (parent != null) //noinspection ResultOfMethodCallIgnored
                parent.mkdirs();
            copyFile(src, dst);
        } catch (Throwable ignored) {
        }
    }

    private static void copyFile(File src, File dst) throws Exception {
        try (java.io.FileInputStream in = new java.io.FileInputStream(src);
             java.io.FileOutputStream out = new java.io.FileOutputStream(dst, false)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
        }
    }

    private static LinearLayout.LayoutParams weight3(float d, int index) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        if (index == 0) {
            lp.rightMargin = dp(4, d);
        } else if (index == 2) {
            lp.leftMargin = dp(4, d);
        } else {
            lp.leftMargin = dp(4, d);
            lp.rightMargin = dp(4, d);
        }
        return lp;
    }

    private View errorPage(float d, int pad, String path) {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF0B1220);
        root.setPadding(pad, pad + dp(24, d), pad, pad);

        TextView back = new TextView(this);
        back.setText("← 返回");
        back.setTextColor(0xFF00C9A7);
        back.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        back.setTypeface(Typeface.DEFAULT_BOLD);
        back.setOnClickListener(v -> finish());
        root.addView(back);

        TextView title = new TextView(this);
        title.setText("无法打开插件");
        title.setTextColor(0xFFE8EEF7);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setPadding(0, dp(20, d), 0, dp(8, d));
        root.addView(title);

        TextView body = new TextView(this);
        body.setText("读不到 plugin.json。\n\n路径:\n" + path
                + "\n\nexists=" + new File(path).exists()
                + "  isDir=" + new File(path).isDirectory()
                + "  canRead=" + new File(path).canRead()
                + "\n\n常见原因：文件权限过严（-rw-rw----）或跨应用 media 目录不可读。"
                + "\n可在电脑执行：\nadb shell chmod -R a+rX \"" + path + "\"");
        body.setTextColor(0xFF8B9BB4);
        body.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        body.setLineSpacing(dp(2, d), 1f);
        root.addView(body);
        return root;
    }

    private void bind() {
        plugin = PluginModels.loadOne(pluginDir);
        if (plugin == null) return;

        statusChip.setText(plugin.enabled ? R.string.badge_on : R.string.badge_off);
        statusChip.setTextColor(plugin.enabled ? 0xFF00C9A7 : 0xFFFF6B7A);
        statusChip.setBackgroundResource(plugin.enabled ? R.drawable.bg_chip_on : R.drawable.bg_chip_off);

        String target = empty(plugin.targetPackage) ? "(未设置)" : plugin.targetPackage;
        String ver = empty(plugin.version) ? "-" : plugin.version;
        String desc = empty(plugin.desc) ? "(无描述)" : plugin.desc;
        metaBody.setText(
                "名称    " + plugin.name + "\n"
                        + "ID      " + plugin.id + "\n"
                        + "版本    " + ver + "\n"
                        + "宿主    " + target + "\n"
                        + "状态    " + (plugin.enabled ? "启用 (.enabled)" : "关闭") + "\n"
                        + "Hooks   " + plugin.hooks.size() + "\n"
                        + "描述    " + desc + "\n"
                        + "路径    " + pluginDir.getAbsolutePath()
        );

        float d = getResources().getDisplayMetrics().density;
        hooksBox.removeAllViews();
        List<PluginModels.Hook> hooks = plugin.hooks;
        if (hooks == null || hooks.isEmpty()) {
            TextView empty = new TextView(this);
            empty.setText("hooks.json 为空（当前运行时只执行 hooks.json）");
            empty.setTextColor(0xFF8B9BB4);
            empty.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
            hooksBox.addView(empty);
        } else {
            for (int i = 0; i < hooks.size(); i++) {
                if (i > 0) {
                    View div = new View(this);
                    div.setBackgroundColor(0xFF2A3650);
                    LinearLayout.LayoutParams dLp = new LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT, dp(1, d));
                    dLp.topMargin = dp(10, d);
                    dLp.bottomMargin = dp(10, d);
                    hooksBox.addView(div, dLp);
                }
                hooksBox.addView(hookRow(d, i, hooks.get(i)));
            }
        }

        StringBuilder files = new StringBuilder();
        File[] kids = pluginDir.listFiles();
        if (kids == null || kids.length == 0) {
            files.append("(空目录)");
        } else {
            java.util.Arrays.sort(kids, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));
            for (File f : kids) {
                files.append(f.isDirectory() ? "d " : "  ")
                        .append(f.getName());
                if (f.isFile()) files.append("  (").append(f.length()).append(" B)");
                files.append('\n');
            }
        }
        filesBody.setText(files.toString().trim());
    }

    private View hookRow(float d, int idx, PluginModels.Hook h) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);

        TextView head = new TextView(this);
        head.setText("#" + idx + "  " + h.kind);
        head.setTextColor(0xFF00C9A7);
        head.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        head.setTypeface(Typeface.DEFAULT_BOLD);
        row.addView(head);

        TextView body = new TextView(this);
        body.setText(h.className + "\n." + h.methodName);
        body.setTextColor(0xFFE8EEF7);
        body.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        body.setTypeface(Typeface.MONOSPACE);
        body.setPadding(0, dp(4, d), 0, 0);
        row.addView(body);

        if (h.returnValue != null && !h.returnValue.isEmpty()) {
            TextView rv = new TextView(this);
            rv.setText("return  " + h.returnValue);
            rv.setTextColor(0xFF8B9BB4);
            rv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
            rv.setPadding(0, dp(2, d), 0, 0);
            row.addView(rv);
        }
        if (h.note != null && !h.note.isEmpty()) {
            TextView note = new TextView(this);
            note.setText(h.note);
            note.setTextColor(0xFF5C6B82);
            note.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
            note.setPadding(0, dp(2, d), 0, 0);
            row.addView(note);
        }
        return row;
    }

    private void toggleEnabled(Button toggleBtn) {
        File marker = new File(pluginDir, ".enabled");
        try {
            if (marker.isFile()) {
                //noinspection ResultOfMethodCallIgnored
                marker.delete();
                Toast.makeText(this, "已禁用（请强停宿主后重开）", Toast.LENGTH_SHORT).show();
            } else {
                //noinspection ResultOfMethodCallIgnored
                marker.createNewFile();
                Toast.makeText(this, "已启用（请强停宿主后重开）", Toast.LENGTH_SHORT).show();
            }
        } catch (Throwable t) {
            Toast.makeText(this, "切换失败: " + t.getMessage(), Toast.LENGTH_LONG).show();
        }
        plugin = PluginModels.loadOne(pluginDir);
        if (plugin != null) {
            toggleBtn.setText(plugin.enabled ? "禁用插件" : "启用插件");
        }
        bind();
    }

    private void openHostApp() {
        if (plugin == null || empty(plugin.targetPackage)) {
            Toast.makeText(this, "未设置 targetPackage", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            Intent launch = getPackageManager().getLaunchIntentForPackage(plugin.targetPackage);
            if (launch == null) {
                Toast.makeText(this, "找不到宿主启动入口: " + plugin.targetPackage, Toast.LENGTH_LONG).show();
                return;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(launch);
        } catch (Throwable t) {
            Toast.makeText(this, "打开失败: " + t.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private static boolean empty(String s) {
        return s == null || s.isEmpty();
    }

    private TextView chip(float d, String text, int color, int bg) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(color);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setBackgroundResource(bg);
        t.setPadding(dp(12, d), dp(5, d), dp(12, d), dp(5, d));
        return t;
    }

    private TextView section(float d, String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(0xFF8B9BB4);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setAllCaps(true);
        t.setLetterSpacing(0.06f);
        return t;
    }

    private TextView cardText(float d) {
        TextView t = new TextView(this);
        t.setTextColor(0xFFE8EEF7);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        t.setLineSpacing(dp(2, d), 1f);
        return t;
    }

    private View wrapCard(float d, View child) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        int pad = dp(16, d);
        card.setPadding(pad, pad, pad, pad);
        card.addView(child, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return card;
    }

    private Button primaryButton(float d, String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(0xFF0B1220);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setBackgroundResource(R.drawable.bg_btn_primary);
        b.setMinHeight(dp(48, d));
        return b;
    }

    private Button ghostButton(float d, String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(0xFF00C9A7);
        b.setBackgroundResource(R.drawable.bg_btn_ghost);
        b.setMinHeight(dp(48, d));
        return b;
    }

    private static LinearLayout.LayoutParams weightLp(float d, boolean first) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        if (first) lp.rightMargin = dp(6, d);
        else lp.leftMargin = dp(6, d);
        return lp;
    }

    private static LinearLayout.LayoutParams sectionLp(float d) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(18, d);
        lp.bottomMargin = dp(8, d);
        return lp;
    }

    private static LinearLayout.LayoutParams cardLp() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private static int dp(int v, float d) {
        return Math.round(v * d);
    }
}
