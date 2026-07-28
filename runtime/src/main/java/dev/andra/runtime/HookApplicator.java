package dev.andra.runtime;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Locale;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Apply hooks.json entries without BeanShell (phase-1 runtime).
 * Supports kind: log | before | after | replace.
 * <p>
 * Optional note tokens:
 * <ul>
 *   <li>{@code log_result} — after hook, log return value</li>
 * </ul>
 * App-specific automation belongs in plugins / external modules, not the core runtime.
 */
public final class HookApplicator {
    private HookApplicator() {}

    public static void apply(PluginModels.Plugin plugin, XC_LoadPackage.LoadPackageParam lpparam) {
        if (plugin == null || plugin.hooks == null || plugin.hooks.isEmpty()) {
            AndraLog.d(safe(plugin), "无 hooks.json（main.bsh 仅作文档）");
            return;
        }
        ClassLoader cl = lpparam.classLoader;
        int ok = 0;
        for (int i = 0; i < plugin.hooks.size(); i++) {
            PluginModels.Hook h = plugin.hooks.get(i);
            try {
                installOne(cl, h, i);
                ok++;
            } catch (Throwable t) {
                AndraLog.e(plugin.name, "Hook 安装失败 [" + i + "] "
                        + h.className + "." + h.methodName, t);
            }
        }
        AndraLog.d(plugin.name, "Hook 就绪 " + ok + "/" + plugin.hooks.size());
    }

    private static String safe(PluginModels.Plugin p) {
        return p == null ? "?" : p.name;
    }

    private static void installOne(ClassLoader cl, PluginModels.Hook h, int idx) {
        Class<?> clazz = XposedHelpers.findClass(h.className, cl);
        String kind = h.kind == null ? "log" : h.kind.toLowerCase(Locale.US);
        final boolean logResult = noteHas(h.note, "log_result") || "log".equals(kind);
        switch (kind) {
            case "replace":
            case "before":
                hookAll(clazz, h.methodName, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if ("replace".equals(kind) || h.returnValue != null) {
                            Object v = parseReturn(h.returnValue, param.method);
                            param.setResult(v);
                        } else {
                            AndraLog.d("[" + idx + "] 调用前 " + h.methodName
                                    + " 参数=" + Arrays.toString(param.args));
                        }
                    }
                });
                break;
            case "after":
                hookAll(clazz, h.methodName, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (h.returnValue != null) {
                            param.setResult(parseReturn(h.returnValue, param.method));
                        }
                        if (logResult) {
                            AndraLog.d("[" + idx + "] 调用后 " + h.methodName
                                    + " 结果=" + param.getResult()
                                    + " 参数=" + Arrays.toString(param.args));
                        }
                    }
                });
                break;
            case "log":
            default:
                hookAll(clazz, h.methodName, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        AndraLog.d("[" + idx + "] 调用 " + h.className + "." + h.methodName
                                + " 参数=" + Arrays.toString(param.args));
                    }

                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        AndraLog.d("[" + idx + "] 返回 " + h.className + "." + h.methodName
                                + " 结果=" + param.getResult());
                    }
                });
                break;
        }
        AndraLog.d("已挂接 " + kind + " " + h.className + "." + h.methodName);
    }

    private static boolean noteHas(String note, String token) {
        if (note == null || note.isEmpty() || token == null) return false;
        String n = note.toLowerCase(Locale.US);
        String t = token.toLowerCase(Locale.US);
        return n.contains(t);
    }

    private static void hookAll(Class<?> clazz, String methodName, XC_MethodHook hook) {
        boolean any = false;
        // Walk superclasses: host often overrides onCreate only on base Activity.
        for (Class<?> c = clazz; c != null && c != Object.class; c = c.getSuperclass()) {
            Method[] methods;
            try {
                methods = c.getDeclaredMethods();
            } catch (Throwable t) {
                break;
            }
            for (Method m : methods) {
                if (!m.getName().equals(methodName)) continue;
                try {
                    XposedBridge.hookMethod(m, hook);
                    any = true;
                } catch (Throwable t) {
                    AndraLog.d("挂接软失败 " + c.getName() + "." + methodName + ": " + t);
                }
            }
            if (any && ("onCreate".equals(methodName)
                    || "onResume".equals(methodName)
                    || "onStart".equals(methodName))) {
                break;
            }
        }
        if (!any) {
            throw new NoSuchMethodError(clazz.getName() + "." + methodName);
        }
    }

    private static Object parseReturn(String expr, Object method) {
        if (expr == null || "null".equals(expr)) return null;
        String e = expr.trim();
        if ("true".equals(e)) return Boolean.TRUE;
        if ("false".equals(e)) return Boolean.FALSE;
        if ((e.startsWith("\"") && e.endsWith("\"")) || (e.startsWith("'") && e.endsWith("'"))) {
            return e.substring(1, e.length() - 1);
        }
        try {
            if (e.contains(".")) return Double.parseDouble(e);
            return Integer.parseInt(e);
        } catch (NumberFormatException ignored) {
        }
        try {
            if (e.endsWith("L") || e.endsWith("l")) {
                return Long.parseLong(e.substring(0, e.length() - 1));
            }
        } catch (NumberFormatException ignored) {
        }
        AndraLog.d("无法解析返回值 '" + expr + "'，使用 null");
        return null;
    }
}
