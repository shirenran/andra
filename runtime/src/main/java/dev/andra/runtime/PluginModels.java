package dev.andra.runtime;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** plugin.json + hooks.json models. */
public final class PluginModels {
    private PluginModels() {}

    public static final class Hook {
        public final String className;
        public final String methodName;
        public final String kind;
        public final String returnValue;
        public final String note;

        public Hook(String className, String methodName, String kind, String returnValue, String note) {
            this.className = className;
            this.methodName = methodName;
            this.kind = kind == null ? "log" : kind;
            this.returnValue = returnValue;
            this.note = note == null ? "" : note;
        }
    }

    public static final class Plugin {
        public final File dir;
        public final String id;
        public final String name;
        public final String targetPackage;
        public final String version;
        public final String desc;
        public final boolean enabled;
        public final List<Hook> hooks;

        public Plugin(
                File dir,
                String id,
                String name,
                String targetPackage,
                String version,
                String desc,
                boolean enabled,
                List<Hook> hooks) {
            this.dir = dir;
            this.id = id;
            this.name = name;
            this.targetPackage = targetPackage;
            this.version = version;
            this.desc = desc;
            this.enabled = enabled;
            this.hooks = hooks;
        }
    }

    public static List<Plugin> loadAll(File pluginsRoot) {
        List<Plugin> out = new ArrayList<>();
        if (pluginsRoot == null || !pluginsRoot.isDirectory()) return out;
        File[] children = pluginsRoot.listFiles();
        if (children == null) return out;
        for (File dir : children) {
            if (!dir.isDirectory()) continue;
            Plugin p = loadOne(dir);
            if (p != null) out.add(p);
        }
        return out;
    }

    public static Plugin loadOne(File dir) {
        File pj = new File(dir, "plugin.json");
        if (!pj.isFile()) return null;
        try {
            String raw = AndraIo.readUtf8(pj);
            JSONObject o = new JSONObject(raw);
            String id = o.optString("id", dir.getName());
            String name = o.optString("name", id);
            String target = o.optString("targetPackage", "");
            String version = o.optString("version", "");
            String desc = o.optString("desc", "");
            boolean enabled = new File(dir, ".enabled").isFile();
            List<Hook> hooks = loadHooks(dir, o.optString("hooksFile", "hooks.json"));
            return new Plugin(dir, id, name, target, version, desc, enabled, hooks);
        } catch (Throwable t) {
            android.util.Log.w(AndraPaths.TAG, "loadOne failed " + dir + ": " + t);
            return null;
        }
    }

    public static List<Hook> loadHooks(File dir, String hooksFile) {
        List<Hook> hooks = new ArrayList<>();
        File hj = new File(dir, hooksFile == null || hooksFile.isEmpty() ? "hooks.json" : hooksFile);
        if (!hj.isFile()) return hooks;
        try {
            JSONArray arr = new JSONArray(AndraIo.readUtf8(hj));
            for (int i = 0; i < arr.length(); i++) {
                JSONObject h = arr.getJSONObject(i);
                hooks.add(new Hook(
                        h.getString("class_name"),
                        h.getString("method_name"),
                        h.optString("kind", "log"),
                        h.has("return_value") && !h.isNull("return_value")
                                ? String.valueOf(h.get("return_value"))
                                : null,
                        h.optString("note", "")
                ));
            }
        } catch (Throwable ignored) {
        }
        return hooks;
    }
}
