package dev.andra.runtime;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Andra companion UI — dark card layout for runtime status, plugins, paths.
 */
public final class StatusActivity extends Activity {
    private LinearLayout pluginList;
    private TextView deployBody;
    private TextView pathBody;
    private TextView statusChip;
    private TextView versionChip;
    private TextView emptyPlugins;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 23) {
            getWindow().setStatusBarColor(0xFF0B1220);
            getWindow().setNavigationBarColor(0xFF0B1220);
        }

        float d = getResources().getDisplayMetrics().density;
        int pad = dp(16, d);
        int gap = dp(12, d);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF0B1220);

        // ----- Header -----
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setBackgroundResource(R.drawable.bg_header);
        header.setPadding(pad, pad + dp(8, d), pad, pad);

        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setOrientation(LinearLayout.HORIZONTAL);
        titleRow.setGravity(Gravity.CENTER_VERTICAL);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_launcher_foreground);
        logo.setBackgroundResource(R.drawable.bg_icon_plate);
        int logoSize = dp(52, d);
        LinearLayout.LayoutParams logoLp = new LinearLayout.LayoutParams(logoSize, logoSize);
        logo.setPadding(dp(4, d), dp(4, d), dp(4, d), dp(4, d));
        titleRow.addView(logo, logoLp);

        LinearLayout titleCol = new LinearLayout(this);
        titleCol.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams titleColLp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        titleColLp.leftMargin = dp(12, d);
        titleRow.addView(titleCol, titleColLp);

        TextView title = new TextView(this);
        title.setText(R.string.app_name);
        title.setTextColor(0xFFE8EEF7);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        titleCol.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText(R.string.app_subtitle);
        subtitle.setTextColor(0xFF8B9BB4);
        subtitle.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        titleCol.addView(subtitle);

        header.addView(titleRow);

        LinearLayout chipRow = new LinearLayout(this);
        chipRow.setOrientation(LinearLayout.HORIZONTAL);
        chipRow.setPadding(0, dp(14, d), 0, 0);

        statusChip = chip(d, "扫描中…", 0xFF8B9BB4, R.drawable.bg_chip_neutral);
        versionChip = chip(d, versionLabel(), 0xFF00C9A7, R.drawable.bg_chip_on);
        chipRow.addView(statusChip);
        LinearLayout.LayoutParams vLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        vLp.leftMargin = dp(8, d);
        chipRow.addView(versionChip, vLp);
        header.addView(chipRow);

        root.addView(header, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        // ----- Scroll content -----
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(pad, pad, pad, pad + dp(24, d));
        scroll.addView(content);

        // Actions: refresh + copy path
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setWeightSum(2f);

        Button refresh = primaryButton(d, getString(R.string.action_refresh));
        refresh.setOnClickListener(v -> render());
        actions.addView(refresh, actionLp(d, true));

        Button copyPath = ghostButton(d, getString(R.string.action_copy_path));
        copyPath.setOnClickListener(v -> {
            String path = AndraPaths.resolvePluginsDir().getAbsolutePath();
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null) {
                cm.setPrimaryClip(ClipData.newPlainText("andra-plugins", path));
                Toast.makeText(this, "已复制\n" + path, Toast.LENGTH_SHORT).show();
            }
        });
        actions.addView(copyPath, actionLp(d, false));
        content.addView(actions);

        // Deploy card
        content.addView(sectionLabel(d, R.string.section_deploy), sectionLp(d));
        deployBody = cardText(d);
        content.addView(wrapCard(d, deployBody), cardLp(d));

        // Plugins card
        content.addView(sectionLabel(d, R.string.section_plugins), sectionLp(d));
        LinearLayout pluginsCard = new LinearLayout(this);
        pluginsCard.setOrientation(LinearLayout.VERTICAL);
        pluginsCard.setBackgroundResource(R.drawable.bg_card);
        pluginsCard.setPadding(pad, pad, pad, pad);
        emptyPlugins = new TextView(this);
        emptyPlugins.setText(R.string.empty_plugins);
        emptyPlugins.setTextColor(0xFF8B9BB4);
        emptyPlugins.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        emptyPlugins.setLineSpacing(0, 1.25f);
        pluginsCard.addView(emptyPlugins);
        pluginList = new LinearLayout(this);
        pluginList.setOrientation(LinearLayout.VERTICAL);
        pluginsCard.addView(pluginList);
        content.addView(pluginsCard, cardLp(d));

        // Paths card
        content.addView(sectionLabel(d, R.string.section_paths), sectionLp(d));
        pathBody = cardText(d);
        pathBody.setTypeface(Typeface.MONOSPACE);
        pathBody.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        content.addView(wrapCard(d, pathBody), cardLp(d));

        // Guide card
        content.addView(sectionLabel(d, R.string.section_guide), sectionLp(d));
        TextView guide = cardText(d);
        guide.setText(R.string.guide_body);
        guide.setLineSpacing(dp(2, d), 1f);
        content.addView(wrapCard(d, guide), cardLp(d));

        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);
        render();
    }

    @Override
    protected void onResume() {
        super.onResume();
        render();
    }

    private void render() {
        versionChip.setText(versionLabel());

        // last deploy
        File last = AndraPaths.lastDeploy();
        if (last.isFile()) {
            try {
                String raw = AndraIo.readUtf8(last).trim();
                deployBody.setText(prettyJsonish(raw));
            } catch (Throwable t) {
                deployBody.setText("读取失败: " + t.getMessage());
            }
        } else {
            deployBody.setText(getString(R.string.empty_deploy));
        }

        // plugins from all candidate roots (dedupe by id/name)
        Map<String, PluginModels.Plugin> merged = new LinkedHashMap<>();
        List<File> roots = pluginRoots();
        for (File root : roots) {
            for (PluginModels.Plugin p : PluginModels.loadAll(root)) {
                String key = (p.id != null && !p.id.isEmpty()) ? p.id : p.name;
                if (!merged.containsKey(key) || p.enabled) {
                    merged.put(key, p);
                }
            }
        }
        pluginList.removeAllViews();
        if (merged.isEmpty()) {
            emptyPlugins.setVisibility(View.VISIBLE);
            statusChip.setText("0 插件");
            statusChip.setTextColor(0xFF8B9BB4);
            statusChip.setBackgroundResource(R.drawable.bg_chip_neutral);
        } else {
            emptyPlugins.setVisibility(View.GONE);
            int on = 0;
            float d = getResources().getDisplayMetrics().density;
            boolean first = true;
            for (PluginModels.Plugin p : merged.values()) {
                if (p.enabled) on++;
                if (!first) {
                    View divider = new View(this);
                    divider.setBackgroundColor(0xFF2A3650);
                    LinearLayout.LayoutParams dLp = new LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT, dp(1, d));
                    dLp.topMargin = dp(10, d);
                    dLp.bottomMargin = dp(10, d);
                    pluginList.addView(divider, dLp);
                }
                first = false;
                pluginList.addView(pluginRow(d, p));
            }
            statusChip.setText(on + "/" + merged.size() + " 启用");
            if (on > 0) {
                statusChip.setTextColor(0xFF00C9A7);
                statusChip.setBackgroundResource(R.drawable.bg_chip_on);
            } else {
                statusChip.setTextColor(0xFFFF6B7A);
                statusChip.setBackgroundResource(R.drawable.bg_chip_off);
            }
        }

        // paths
        StringBuilder paths = new StringBuilder();
        paths.append("resolve  ").append(AndraPaths.resolvePluginsDir().getAbsolutePath()).append('\n');
        paths.append("public   ").append(AndraPaths.pluginsDir().getAbsolutePath()).append('\n');
        paths.append("media    ").append(AndraPaths.mediaPluginsDir().getAbsolutePath()).append('\n');
        paths.append("legacy   ").append(AndraPaths.legacyPluginsDir().getAbsolutePath()).append('\n');
        paths.append("host eg  ").append(
                AndraPaths.hostMediaPluginsDir("com.android.settings") != null
                        ? AndraPaths.hostMediaPluginsDir("com.android.settings").getAbsolutePath()
                        : "-");
        pathBody.setText(paths.toString());
    }

    private List<File> pluginRoots() {
        List<File> roots = new ArrayList<>();
        // Prefer app-private mirror (always readable by this UI process).
        addUnique(roots, AndraPaths.appPrivatePluginsDir(this));
        File resolved = AndraPaths.resolvePluginsDir();
        addUnique(roots, resolved);
        addUnique(roots, AndraPaths.pluginsDir());
        addUnique(roots, AndraPaths.mediaPluginsDir());
        addUnique(roots, AndraPaths.legacyPluginsDir());
        // Demo / settings host media root (example only)
        addUnique(roots, AndraPaths.hostMediaPluginsDir("com.android.settings"));
        // scan /sdcard/Android/media/*/Andra/plugins lightly
        try {
            File media = new File(android.os.Environment.getExternalStorageDirectory(), "Android/media");
            File[] hosts = media.listFiles();
            if (hosts != null) {
                int n = 0;
                for (File host : hosts) {
                    if (!host.isDirectory()) continue;
                    File p = new File(host, "Andra/plugins");
                    if (p.isDirectory()) {
                        addUnique(roots, p);
                        if (++n >= 12) break;
                    }
                }
            }
        } catch (Throwable ignored) {
        }
        return roots;
    }

    private static void addUnique(List<File> roots, File f) {
        if (f == null) return;
        String path = f.getAbsolutePath();
        for (File e : roots) {
            if (e.getAbsolutePath().equals(path)) return;
        }
        roots.add(f);
    }

    private View pluginRow(float d, PluginModels.Plugin p) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setBackgroundResource(R.drawable.bg_row_press);
        row.setClickable(true);
        row.setFocusable(true);
        row.setPadding(dp(4, d), dp(6, d), dp(4, d), dp(6, d));
        final File dirFile = p.dir;
        row.setOnClickListener(v -> {
            if (dirFile == null) {
                Toast.makeText(this, "插件路径无效", Toast.LENGTH_SHORT).show();
                return;
            }
            PluginDetailActivity.open(this, dirFile);
        });

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);

        TextView name = new TextView(this);
        name.setText(p.name);
        name.setTextColor(0xFFE8EEF7);
        name.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        name.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        top.addView(name, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        TextView badge = new TextView(this);
        badge.setText(p.enabled ? R.string.badge_on : R.string.badge_off);
        badge.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        badge.setTypeface(Typeface.DEFAULT_BOLD);
        badge.setPadding(dp(10, d), dp(3, d), dp(10, d), dp(3, d));
        if (p.enabled) {
            badge.setTextColor(0xFF00C9A7);
            badge.setBackgroundResource(R.drawable.bg_chip_on);
        } else {
            badge.setTextColor(0xFFFF6B7A);
            badge.setBackgroundResource(R.drawable.bg_chip_off);
        }
        top.addView(badge);

        TextView chevron = new TextView(this);
        chevron.setText(" ›");
        chevron.setTextColor(0xFF5C6B82);
        chevron.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        chevron.setPadding(dp(6, d), 0, 0, 0);
        top.addView(chevron);
        row.addView(top);

        TextView meta = new TextView(this);
        String target = (p.targetPackage == null || p.targetPackage.isEmpty())
                ? "(未设置 targetPackage)"
                : p.targetPackage;
        String ver = (p.version == null || p.version.isEmpty()) ? "-" : p.version;
        meta.setText(target + "  ·  v" + ver + "  ·  hooks " + p.hooks.size() + "  ·  点击查看");
        meta.setTextColor(0xFF8B9BB4);
        meta.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        meta.setPadding(0, dp(4, d), 0, 0);
        row.addView(meta);

        if (p.desc != null && !p.desc.isEmpty()) {
            TextView desc = new TextView(this);
            desc.setText(p.desc);
            desc.setTextColor(0xFF5C6B82);
            desc.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
            desc.setPadding(0, dp(2, d), 0, 0);
            row.addView(desc);
        }

        TextView dir = new TextView(this);
        dir.setText(p.dir != null ? p.dir.getAbsolutePath() : "");
        dir.setTextColor(0xFF5C6B82);
        dir.setTextSize(TypedValue.COMPLEX_UNIT_SP, 10);
        dir.setTypeface(Typeface.MONOSPACE);
        dir.setPadding(0, dp(4, d), 0, 0);
        row.addView(dir);
        return row;
    }

    private String versionLabel() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return "v" + pi.versionName;
        } catch (Throwable t) {
            return "v?";
        }
    }

    private static String prettyJsonish(String raw) {
        // lightweight indent for last_deploy.json readability
        try {
            String s = raw.trim();
            if (!s.startsWith("{")) return raw;
            StringBuilder out = new StringBuilder();
            int indent = 0;
            boolean inStr = false;
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                if (c == '"' && (i == 0 || s.charAt(i - 1) != '\\')) inStr = !inStr;
                if (!inStr && (c == '{' || c == '[')) {
                    out.append(c).append('\n');
                    indent++;
                    for (int k = 0; k < indent; k++) out.append("  ");
                } else if (!inStr && (c == '}' || c == ']')) {
                    out.append('\n');
                    indent = Math.max(0, indent - 1);
                    for (int k = 0; k < indent; k++) out.append("  ");
                    out.append(c);
                } else if (!inStr && c == ',') {
                    out.append(c).append('\n');
                    for (int k = 0; k < indent; k++) out.append("  ");
                } else if (!inStr && c == ':') {
                    out.append(": ");
                } else if (!inStr && (c == ' ' || c == '\n' || c == '\r' || c == '\t')) {
                    // skip
                } else {
                    out.append(c);
                }
            }
            return out.toString();
        } catch (Throwable t) {
            return raw;
        }
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

    private TextView sectionLabel(float d, int resId) {
        TextView t = new TextView(this);
        t.setText(resId);
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

    private static LinearLayout.LayoutParams actionLp(float d, boolean first) {
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

    private static LinearLayout.LayoutParams cardLp(float d) {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private static int dp(int v, float d) {
        return Math.round(v * d);
    }
}
