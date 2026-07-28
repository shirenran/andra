package dev.andra.runtime;

import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import de.robv.android.xposed.XposedBridge;

/**
 * Unified logging. File format:
 *   MM-dd HH:mm:ss.SSS  LEVEL  [plugin]  message
 *
 * UI only shows {@code I} / {@code E}. Verbose scan/hook lines use {@code D}
 * and stay in the file for adb debugging only.
 */
public final class AndraLog {
    public static final String LEVEL_DEBUG = "D";
    public static final String LEVEL_INFO = "I";
    public static final String LEVEL_ERROR = "E";

    private static final long MAX_BYTES = 512 * 1024L;
    private static final Object LOCK = new Object();
    private static volatile String lastHostPackage = "";

    private AndraLog() {}

    public static void d(String msg) {
        d(null, msg);
    }

    public static void d(String plugin, String msg) {
        write(LEVEL_DEBUG, plugin, msg, null);
    }

    public static void i(String msg) {
        i(null, msg);
    }

    public static void i(String plugin, String msg) {
        write(LEVEL_INFO, plugin, msg, null);
    }

    public static void e(String msg) {
        e(null, msg, null);
    }

    public static void e(String msg, Throwable t) {
        e(null, msg, t);
    }

    public static void e(String plugin, String msg, Throwable t) {
        write(LEVEL_ERROR, plugin, msg, t);
    }

    public static void setHostPackage(String hostPackage) {
        if (hostPackage != null && !hostPackage.isEmpty()) {
            lastHostPackage = hostPackage;
        }
    }

    private static void write(String level, String plugin, String msg, Throwable t) {
        String fullMsg = msg == null ? "" : msg;
        if (t != null) {
            fullMsg = fullMsg + " | " + t;
        }
        String line = format(level, plugin, fullMsg);
        String tagMsg = plugin == null || plugin.isEmpty() ? fullMsg : ("[" + plugin + "] " + fullMsg);
        try {
            if (LEVEL_ERROR.equals(level)) {
                Log.e(AndraPaths.TAG, tagMsg);
            } else if (LEVEL_DEBUG.equals(level)) {
                Log.d(AndraPaths.TAG, tagMsg);
            } else {
                Log.i(AndraPaths.TAG, tagMsg);
            }
        } catch (Throwable ignored) {
        }
        // Keep Xposed bridge for I/E only — reduce LSPosed spam.
        if (!LEVEL_DEBUG.equals(level)) {
            try {
                XposedBridge.log(AndraPaths.TAG + "/" + level + ": " + tagMsg);
            } catch (Throwable ignored) {
            }
            if (t != null) {
                try {
                    XposedBridge.log(t);
                } catch (Throwable ignored) {
                }
            }
        }
        appendToFiles(line);
    }

    private static String format(String level, String plugin, String msg) {
        String ts = new SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.US).format(new Date());
        String p = (plugin == null || plugin.isEmpty()) ? "-" : plugin;
        String lv = level == null ? LEVEL_INFO : level;
        return ts + "  " + lv + "  [" + p + "]  " + msg;
    }

    private static void appendToFiles(String line) {
        synchronized (LOCK) {
            for (File f : writeTargets()) {
                try {
                    File parent = f.getParentFile();
                    if (parent != null && !parent.exists()) {
                        //noinspection ResultOfMethodCallIgnored
                        parent.mkdirs();
                    }
                    rotateIfNeeded(f);
                    try (FileOutputStream out = new FileOutputStream(f, true)) {
                        out.write((line + "\n").getBytes(StandardCharsets.UTF_8));
                    }
                    try {
                        //noinspection ResultOfMethodCallIgnored
                        f.setReadable(true, false);
                        //noinspection ResultOfMethodCallIgnored
                        f.setWritable(true, false);
                        if (parent != null) {
                            //noinspection ResultOfMethodCallIgnored
                            parent.setReadable(true, false);
                            //noinspection ResultOfMethodCallIgnored
                            parent.setExecutable(true, false);
                            //noinspection ResultOfMethodCallIgnored
                            parent.setWritable(true, false);
                        }
                    } catch (Throwable ignored) {
                    }
                } catch (Throwable ignored) {
                }
            }
        }
    }

    private static List<File> writeTargets() {
        List<File> out = new ArrayList<>();
        File base = android.os.Environment.getExternalStorageDirectory();
        String host = lastHostPackage;
        if (host != null && !host.isEmpty()) {
            add(out, new File(base, "Android/media/" + host + "/Andra/logs/andra.log"));
        }
        add(out, new File(base, "Andra/logs/andra.log"));
        add(out, new File(base, "Android/data/" + AndraPaths.RUNTIME_PKG + "/files/logs/andra.log"));
        return out;
    }

    public static List<File> logFileCandidates(String hostPackage) {
        List<File> out = new ArrayList<>();
        File base = android.os.Environment.getExternalStorageDirectory();
        String host = (hostPackage != null && !hostPackage.isEmpty()) ? hostPackage : lastHostPackage;
        if (host != null && !host.isEmpty()) {
            add(out, new File(base, "Android/media/" + host + "/Andra/logs/andra.log"));
        }
        add(out, new File(base, "Andra/logs/andra.log"));
        add(out, new File(base, "Android/data/" + AndraPaths.RUNTIME_PKG + "/files/logs/andra.log"));
        try {
            File media = new File(base, "Android/media");
            File[] hosts = media.listFiles();
            if (hosts != null) {
                int n = 0;
                for (File h : hosts) {
                    File f = new File(h, "Andra/logs/andra.log");
                    if (f.isFile()) {
                        add(out, f);
                        if (++n >= 8) break;
                    }
                }
            }
        } catch (Throwable ignored) {
        }
        return out;
    }

    private static void add(List<File> out, File f) {
        if (f == null) return;
        for (File e : out) {
            if (e.getAbsolutePath().equals(f.getAbsolutePath())) return;
        }
        out.add(f);
    }

    private static void rotateIfNeeded(File f) {
        try {
            if (!f.isFile() || f.length() < MAX_BYTES) return;
            File bak = new File(f.getAbsolutePath() + ".1");
            //noinspection ResultOfMethodCallIgnored
            bak.delete();
            //noinspection ResultOfMethodCallIgnored
            f.renameTo(bak);
        } catch (Throwable ignored) {
        }
    }

    /**
     * Read recent lines for UI. Only Info + Error by default.
     *
     * @param infoAndErrorOnly if true, drop Debug and noisy legacy lines
     */
    public static String readRecent(String pluginFilter, String hostPackage, int maxLines,
                                    boolean infoAndErrorOnly) {
        if (maxLines <= 0) maxLines = 120;
        List<String> merged = new ArrayList<>();
        for (File f : logFileCandidates(hostPackage)) {
            try {
                // canRead() may be false for 660 files; still attempt open
                if (!f.isFile()) continue;
                for (String line : readTailLines(f, Math.max(maxLines * 4, 200))) {
                    if (infoAndErrorOnly && !keepForUi(line, pluginFilter, hostPackage)) {
                        continue;
                    }
                    if (!infoAndErrorOnly && pluginFilter != null && !pluginFilter.isEmpty()) {
                        if (!lineContainsPlugin(line, pluginFilter, hostPackage)) continue;
                    }
                    merged.add(line);
                }
            } catch (Throwable ignored) {
            }
        }

        // logcat: only Andra I/E when filtering for UI
        try {
            for (String line : dumpLogcat(Math.min(200, maxLines * 2))) {
                if (infoAndErrorOnly) {
                    if (!lineLooksInfoOrErrorLogcat(line)) continue;
                    if (pluginFilter != null && !pluginFilter.isEmpty()
                            && !line.toLowerCase(Locale.US).contains(pluginFilter.toLowerCase(Locale.US))
                            && (hostPackage == null || !line.contains(hostPackage))) {
                        // keep generic Andra I/E without plugin name
                        if (!line.contains("Andra")) continue;
                    }
                } else if (!line.contains("Andra")) {
                    continue;
                }
                merged.add(line);
            }
        } catch (Throwable ignored) {
        }

        if (merged.isEmpty()) {
            return "（暂无信息/错误日志）\n\n打开宿主 App 触发后点「刷新日志」。";
        }

        List<String> dedup = new ArrayList<>();
        String prev = null;
        for (String line : merged) {
            if (line.equals(prev)) continue;
            dedup.add(line);
            prev = line;
        }
        // Newest first for UI (倒序).
        int from = Math.max(0, dedup.size() - maxLines);
        StringBuilder sb = new StringBuilder();
        for (int i = dedup.size() - 1; i >= from; i--) {
            sb.append(dedup.get(i)).append('\n');
        }
        return sb.toString().trim();
    }

    /** UI helper: Info + Error only. */
    public static String readRecent(String pluginFilter, String hostPackage, int maxLines) {
        return readRecent(pluginFilter, hostPackage, maxLines, true);
    }

    /**
     * Keep line for UI:
     * - new format with {@code I} / {@code E}
     * - legacy lines that look like outcomes (done/skip/err, apply failed)
     * Drop: hooked/scan/load/CALL/RET/before/after noise and explicit {@code D}.
     */
    private static boolean keepForUi(String line, String pluginFilter, String hostPackage) {
        if (line == null || line.isEmpty()) return false;
        String s = line.trim();

        // New format: ts  LEVEL  [plugin]  msg
        // e.g. 07-28 17:02:39.264  I  [DemoHook]  ...
        if (looksLeveled(s)) {
            char lv = levelChar(s);
            if (lv == 'D' || lv == 'V' || lv == 'd' || lv == 'v') return false;
            if (lv != 'I' && lv != 'E' && lv != 'W' && lv != 'i' && lv != 'e' && lv != 'w') {
                return false;
            }
            return pluginFilter == null || pluginFilter.isEmpty()
                    || lineContainsPlugin(s, pluginFilter, hostPackage)
                    || isImportantOutcome(s);
        }

        // Legacy (no level): only keep important outcomes, drop hook noise.
        if (isNoise(s)) return false;
        if (!isImportantOutcome(s) && !s.contains(" E ") && !s.contains("/E:")) {
            // allow bare error-ish
            String low = s.toLowerCase(Locale.US);
            if (!(low.contains("error") || low.contains("fail") || low.contains("exception")
                    || low.contains("done") || low.contains("skip") || low.contains("partial"))) {
                return false;
            }
        }
        return pluginFilter == null || pluginFilter.isEmpty()
                || lineContainsPlugin(s, pluginFilter, hostPackage)
                || isImportantOutcome(s);
    }

    private static boolean looksLeveled(String s) {
        // "MM-dd HH:mm:ss.SSS  X  ["
        int sp = s.indexOf("  ");
        if (sp < 8) return false;
        String rest = s.substring(sp).trim();
        return rest.length() >= 3
                && (rest.charAt(0) == 'I' || rest.charAt(0) == 'E' || rest.charAt(0) == 'D'
                || rest.charAt(0) == 'W' || rest.charAt(0) == 'V'
                || rest.charAt(0) == 'i' || rest.charAt(0) == 'e' || rest.charAt(0) == 'd')
                && rest.charAt(1) == ' ';
    }

    private static char levelChar(String s) {
        int sp = s.indexOf("  ");
        if (sp < 0) return '?';
        String rest = s.substring(sp).trim();
        return rest.isEmpty() ? '?' : rest.charAt(0);
    }

    private static boolean isNoise(String s) {
        String low = s.toLowerCase(Locale.US);
        return low.contains(" hooked ")
                || low.contains("hooked after")
                || low.contains("hooked before")
                || low.contains("hooked log")
                || low.contains(" scan pkg=")
                || low.contains(" load pkg=")
                || low.contains(" applying ")
                || low.contains("] call ")
                || low.contains("] ret ")
                || low.contains("] before ")
                || low.contains("] after ")
                || low.contains("children=")
                || low.contains("canread=")
                || low.contains("  d  [");
    }

    private static boolean isImportantOutcome(String s) {
        String low = s.toLowerCase(Locale.US);
        return low.contains("done")
                || low.contains("skip")
                || low.contains("fail")
                || low.contains("error")
                || low.contains("exception")
                || low.contains("partial")
                || low.contains("not logged")
                || low.contains("apply failed")
                || low.contains("logs cleared")
                || low.contains("hook 就绪")
                || low.contains("hook 安装失败");
    }

    private static boolean lineContainsPlugin(String line, String pluginFilter, String hostPackage) {
        if (pluginFilter == null || pluginFilter.isEmpty()) return true;
        if (line.contains(pluginFilter)) return true;
        if (line.contains("[" + pluginFilter + "]")) return true;
        String low = line.toLowerCase(Locale.US);
        if (low.contains(pluginFilter.toLowerCase(Locale.US))) return true;
        return hostPackage != null && line.contains(hostPackage);
    }

    private static boolean lineLooksInfoOrErrorLogcat(String line) {
        // logcat: "I/Andra" or "E/Andra" or our file-mirrored content
        if (line.contains("E/Andra") || line.contains("Andra/E")) return true;
        if (line.contains("I/Andra") || line.contains("Andra/I")) return true;
        if (line.contains("  E  [") || line.contains("  I  [")) return true;
        return isImportantOutcome(line) && !isNoise(line);
    }

    public static void clearFiles(String hostPackage) {
        synchronized (LOCK) {
            for (File f : logFileCandidates(hostPackage)) {
                try {
                    if (f.isFile()) {
                        //noinspection ResultOfMethodCallIgnored
                        f.delete();
                    }
                    File bak = new File(f.getAbsolutePath() + ".1");
                    //noinspection ResultOfMethodCallIgnored
                    bak.delete();
                } catch (Throwable ignored) {
                }
            }
        }
    }

    private static List<String> readTailLines(File f, int maxLines) throws Exception {
        List<String> lines = new ArrayList<>();
        long len = f.length();
        long start = Math.max(0, len - Math.min(len, MAX_BYTES));
        try (RandomAccessFile raf = new RandomAccessFile(f, "r")) {
            raf.seek(start);
            if (start > 0) raf.readLine();
            String line;
            while ((line = raf.readLine()) != null) {
                lines.add(new String(line.getBytes(StandardCharsets.ISO_8859_1), StandardCharsets.UTF_8));
            }
        } catch (Throwable t) {
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(new FileInputStream(f), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) lines.add(line);
            }
        }
        int from = Math.max(0, lines.size() - maxLines);
        return lines.subList(from, lines.size());
    }

    private static List<String> dumpLogcat(int maxLines) {
        List<String> out = new ArrayList<>();
        Process p = null;
        try {
            p = Runtime.getRuntime().exec(new String[]{
                    "logcat", "-d", "-t", String.valueOf(Math.min(300, maxLines * 2)),
                    "-s", "Andra:I", "Andra:E"
            });
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    out.add(line);
                    if (out.size() >= maxLines) break;
                }
            }
            p.waitFor();
        } catch (Throwable ignored) {
        } finally {
            if (p != null) p.destroy();
        }
        return out;
    }
}
