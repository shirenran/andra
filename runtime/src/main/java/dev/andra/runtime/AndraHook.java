package dev.andra.runtime;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * LSPosed entry: for each host process, load enabled Andra plugins whose
 * targetPackage matches, and apply hooks.json.
 */
public final class AndraHook implements IXposedHookLoadPackage {
    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        String pkg = lpparam.packageName;
        if (pkg == null) return;

        if (AndraPaths.RUNTIME_PKG.equals(pkg)) {
            AndraLog.d("跳过自身进程");
            return;
        }

        AndraLog.setHostPackage(pkg);
        File root = AndraPaths.resolvePluginsDir(pkg);
        File[] kids = root.isDirectory() ? root.listFiles() : null;
        AndraLog.d("扫描 包=" + pkg + " 目录=" + root.getAbsolutePath()
                + " 存在=" + root.isDirectory()
                + " 可读=" + root.canRead()
                + " 子项=" + (kids == null ? -1 : kids.length));

        List<PluginModels.Plugin> all = PluginModels.loadAll(root);
        List<PluginModels.Plugin> matched = new ArrayList<>();
        for (PluginModels.Plugin p : all) {
            if (!p.enabled) continue;
            if (p.targetPackage == null || p.targetPackage.isEmpty()) continue;
            if (p.targetPackage.equals(pkg)) matched.add(p);
        }
        if (matched.isEmpty()) {
            if (!all.isEmpty()) {
                AndraLog.d("包 " + pkg + " 无匹配的已启用插件（已扫描 " + all.size() + " 个）");
            }
            return;
        }

        AndraLog.d("加载 " + matched.size() + " 个插件 → " + pkg
                + "（" + lpparam.processName + "）");

        for (PluginModels.Plugin p : matched) {
            try {
                AndraLog.d(p.name, "应用中 v" + p.version + " hooks=" + p.hooks.size());
                HookApplicator.apply(p, lpparam);
            } catch (Throwable t) {
                AndraLog.e(p.name, "插件应用失败", t);
            }
        }
    }
}
