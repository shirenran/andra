package dev.andra.runtime;

import android.os.Environment;

import java.io.File;

public final class AndraPaths {
    public static final String RUNTIME_PKG = "dev.andra.runtime";
    public static final String TAG = "Andra";

    /**
     * Public shared root on external storage. Host app processes can read this
     * under typical storage permissions; Android/data/&lt;other-pkg&gt; is blocked,
     * and Android/media/&lt;other-pkg&gt; is often FUSE-broken across processes.
     */
    public static final String SHARED_FILES_REL = "Andra";

    /** Media fallback: /sdcard/Android/media/dev.andra.runtime/files */
    public static final String MEDIA_FILES_REL =
            "Android/media/" + RUNTIME_PKG + "/files";

    /** Legacy path: /sdcard/Android/data/dev.andra.runtime/files */
    public static final String LEGACY_FILES_REL =
            "Android/data/" + RUNTIME_PKG + "/files";

    private AndraPaths() {}

    /** Preferred: /sdcard/Andra */
    public static File filesRoot() {
        File base = Environment.getExternalStorageDirectory();
        return new File(base, SHARED_FILES_REL);
    }

    public static File mediaFilesRoot() {
        File base = Environment.getExternalStorageDirectory();
        return new File(base, MEDIA_FILES_REL);
    }

    public static File legacyFilesRoot() {
        File base = Environment.getExternalStorageDirectory();
        return new File(base, LEGACY_FILES_REL);
    }

    public static File pluginsDir() {
        return new File(filesRoot(), "plugins");
    }

    public static File mediaPluginsDir() {
        return new File(mediaFilesRoot(), "plugins");
    }

    public static File legacyPluginsDir() {
        return new File(legacyFilesRoot(), "plugins");
    }

    public static File bridgeDir() {
        return new File(filesRoot(), "bridge");
    }

    /**
     * App-private external files dir (always readable by Andra UI process).
     * Used as a mirror of deployed plugins for the companion UI.
     */
    public static File appPrivatePluginsDir(android.content.Context ctx) {
        if (ctx == null) return null;
        try {
            File base = ctx.getExternalFilesDir(null);
            if (base == null) base = ctx.getFilesDir();
            return new File(base, "plugins");
        } catch (Throwable t) {
            return new File(ctx.getFilesDir(), "plugins");
        }
    }

    public static File lastDeploy() {
        File[] candidates = new File[] {
                new File(bridgeDir(), "last_deploy.json"),
                new File(mediaFilesRoot(), "bridge/last_deploy.json"),
                new File(legacyFilesRoot(), "bridge/last_deploy.json"),
        };
        for (File f : candidates) {
            if (f.isFile()) return f;
        }
        return candidates[0];
    }

    /**
     * Host-owned media path — always readable inside the target app process:
     * /sdcard/Android/media/&lt;hostPkg&gt;/Andra/plugins
     */
    public static File hostMediaPluginsDir(String hostPackage) {
        if (hostPackage == null || hostPackage.isEmpty()) return null;
        File base = Environment.getExternalStorageDirectory();
        return new File(base, "Android/media/" + hostPackage + "/Andra/plugins");
    }

    public static File hostMediaBridgeDir(String hostPackage) {
        if (hostPackage == null || hostPackage.isEmpty()) return null;
        File base = Environment.getExternalStorageDirectory();
        return new File(base, "Android/media/" + hostPackage + "/Andra/bridge");
    }

    /** Resolve plugins dir that actually contains plugin folders. */
    public static File resolvePluginsDir() {
        return resolvePluginsDir(null);
    }

    public static File resolvePluginsDir(String hostPackage) {
        File[] candidates = new File[] {
                hostMediaPluginsDir(hostPackage),
                pluginsDir(),
                mediaPluginsDir(),
                legacyPluginsDir(),
        };
        for (File dir : candidates) {
            if (hasPluginChildren(dir)) return dir;
        }
        // Prefer host media path for future deploys even if empty.
        File host = hostMediaPluginsDir(hostPackage);
        return host != null ? host : pluginsDir();
    }

    private static boolean hasPluginChildren(File dir) {
        if (dir == null || !dir.isDirectory()) return false;
        File[] kids = dir.listFiles();
        if (kids == null) return false;
        for (File f : kids) {
            if (f.isDirectory() && new File(f, "plugin.json").isFile()) return true;
        }
        return false;
    }
}
