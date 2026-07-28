# Andra MCP 怎么用

MCP（Model Context Protocol）让 AI 客户端（Grok / Claude / Cursor 等）直接调用 Andra 工具：  
**读 APK → 搜字符串 → 定位方法 → 写 hooks 插件 → adb 部署 → 读日志验证**。

你不用手写 Xposed 工程；对 AI 说目标，它调工具完成。

---

## 0. 一次性准备

### 手机

1. 安装并启用 **Andra**（`dev.andra.runtime`）
2. LSPosed **作用域只勾目标 App**（例如某吧），不要勾系统框架
3. `adb` 已连接（USB 或无线；不要用 `172.19.*` VPN 假地址）

### 电脑

```bash
cd mcp
uv sync
# 可选：指定 adb / jadx
export ADB_BIN=$(which adb)
export JADX_BIN=$(which jadx)   # 若已安装
```

### 接入 AI 客户端

把 Andra 注册成 MCP server，目录指向本仓库的 `mcp/`：

```toml
[mcp_servers.andra]
command = "uv"
args = ["run", "--directory", "/绝对路径/andra/mcp", "python", "-m", "andra.server"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 600
```

启动后，对话里应能看到工具：`load_apk`、`search_strings`、`write_plugin`、`deploy_plugin`、`verify_plugin` 等。

---

## 1. 你怎么跟 AI 说话

说清楚这四件事即可：

1. **目标**：例如「某吧去信息流广告 / 开屏广告」
2. **APK 路径**：本机上的安装包或 pull 下来的 `base.apk`
3. **包名**：如 `com.example.forum`（以 `pm path` / 应用信息为准）
4. **约束**：只要 Andra 插件；作用域只勾宿主；部署后要 `verify`

示例提示词：

```text
用 andra MCP 给某吧做去广告插件。
- APK：/path/to/forum.apk
- 包名：com.example.forum
- 目标：拦截信息流广告请求 / 让广告位 shouldShow 返回 false
- 流程：load_apk → search_strings → find_usage → decompile → write_plugin → deploy → verify
- find_method 必须带 in_class；不要空等 logcat
```

---

## 2. 完整案例：某吧去广告（方法示意）

> 下列类名、方法名、字符串均为**教学占位**。真实 App 以你自己反编译结果为准；  
> 本仓库**不附带**任何商业 App 的现成去广告插件。

假设：

| 项 | 值 |
|----|-----|
| 俗称 | 某吧 |
| 包名 | `com.example.forum` |
| APK | `~/apks/forum.apk` |
| 目标 | 信息流广告不展示 |

### 第 1 步：加载 APK

AI 调用：

```text
load_apk(path="~/apks/forum.apk", decompile=false)
```

只建索引，**不要**一上来全量 `decompile_all`（大包会很慢）。

### 第 2 步：用字符串找广告相关代码

优先中文/英文业务词，而不是盲扫类名：

```text
search_strings(keyword="广告")
search_strings(keyword="ad_feed")
search_strings(keyword="Advert")
search_strings(keyword="splash_ad")
```

假设命中：

```text
"showFeedAd"  → 某方法常量池
"/c/ad/get"   → 广告接口 path
```

### 第 3 步：字符串 → 谁在用

```text
find_usage(string="showFeedAd")
find_usage(string="/c/ad/get")
```

得到候选，例如：

```text
com.example.forum.ad.FeedAdManager.shouldShowAd()Z
com.example.forum.ad.FeedAdManager.loadAd(Landroid/content/Context;)V
com.example.forum.net.AdApi.getFeedAd()L...
```

### 第 4 步：反编译确认（先缩小范围）

```text
decompile_method(
  class_name="com.example.forum.ad.FeedAdManager",
  method_name="shouldShowAd"
)
```

读代码后判断策略，常见三种：

| 策略 | hooks `kind` | 适用 |
|------|--------------|------|
| 开关直接变 false | `replace` + `"false"` | `boolean shouldShow*()` |
| 加载广告变空操作 | `before` + 提前 `setResult` | `void loadAd(...)` |
| 先观察再动手 | `log` / `after` + `log_result` | 不确定时 |

某吧去广告最省事的一刀往往是：

```json
{
  "class_name": "com.example.forum.ad.FeedAdManager",
  "method_name": "shouldShowAd",
  "kind": "replace",
  "return_value": "false",
  "note": "feed ad gate"
}
```

若还有开屏：

```json
{
  "class_name": "com.example.forum.ad.SplashAdHelper",
  "method_name": "needSplash",
  "kind": "replace",
  "return_value": "false",
  "note": "splash ad gate"
}
```

### 第 5 步：生成插件

```text
write_plugin(
  name="ForumNoAd",
  target_package="com.example.forum",
  hooks=[ ... 上面 JSON ... ],
  desc="某吧信息流/开屏广告开关"
)
```

产物在：

```text
mcp/workspace/plugins/ForumNoAd/
  plugin.json
  hooks.json
  main.bsh
  INSTALL.md
```

**真正生效的是 `hooks.json`**（`main.bsh` 目前主要是文档）。

### 第 6 步：部署到手机

```text
adb_connect(address="192.168.x.x:PORT")   # 若尚未连接
deploy_plugin(name="ForumNoAd", target_package="com.example.forum")
```

会推到（三路镜像，宿主可读的是 media）：

```text
/sdcard/Android/media/com.example.forum/Andra/plugins/ForumNoAd/
```

### 第 7 步：LSPosed + 验证

1. LSPosed → Andra → 作用域勾选 **某吧** `com.example.forum`
2. 强停某吧，再打开，滑信息流看广告是否还在

```text
verify_plugin(name="ForumNoAd", host_package="com.example.forum", wait_sec=6)
read_andra_log(host_package="com.example.forum", plugin="ForumNoAd", level="IE")
```

期望日志大意：

```text
I  [ForumNoAd]  Hook 就绪 2/2
```

若没有 Andra 行：先查路径是否存在、作用域是否勾对、是否强停过宿主——**不要**空等 live logcat。

### 第 8 步：不好使就迭代

| 现象 | 下一步 |
|------|--------|
| Hook 就绪但广告还在 | 开关不是这个方法；对 `loadAd` / 网络回调再 `log`，或 `find_caller` |
| 完全无日志 | 插件目录、`.enabled`、LSPosed 作用域、进程名 |
| 类名找不到 | App 更新混淆了；重新 `search_strings` + `find_usage` |
| MCP 卡住 | `find_method` 必须带 `in_class`；大包别全量 decompile |

改 `hooks.json` 后只需再：

```text
deploy_plugin → force-stop 宿主 → verify
```

---

## 3. 工具速查（按推荐顺序）

| 阶段 | 工具 | 说明 |
|------|------|------|
| 加载 | `load_apk` | 索引 APK |
| 定位 | `search_strings` → `find_usage` → `find_caller` | 便宜、稳 |
| 确认 | `decompile_method` / `decompile_class` | 候选 ≤2 个再反编译 |
| 产出 | `write_plugin` | 写出 hooks.json |
| 设备 | `adb_connect` / `device_status` | 无线注意真实 Wi‑Fi IP |
| 部署 | `deploy_plugin` | media + public + 私有三路 |
| 验证 | `verify_plugin` / `read_andra_log` | 优先于 `capture_logcat` |

**禁止/慎用：**

- `find_method` 不带 `in_class` 且无有效方法名模式 → 大包会卡死（工具会拒绝）
- 长时间 live follow logcat
- 把插件只推到 `Android/data/dev.andra.runtime/...`（宿主读不到）

---

## 4. 不用 AI：纯 CLI 等价操作

MCP 背后同一套 CLI：

```bash
cd mcp
uv run python -m andra.cli deploy ForumNoAd --package com.example.forum
uv run python -m andra.cli verify ForumNoAd --package com.example.forum --wait 6
uv run python -m andra.cli read-log --host com.example.forum --plugin ForumNoAd --level IE
```

静态分析也可用本机 jadx；最终仍然是写好 `hooks.json` 再 deploy。

---

## 5. 和「某吧去广告模块」成品的区别

| | 网上成品 Xposed 模块 | Andra MCP 工作流 |
|--|---------------------|------------------|
| 维护 | App 一更新可能失效，等作者 | 自己对当前 APK 再搜字符串迭代 |
| 原理 | 黑盒 APK | 你看得到 hooks 点，可改 |
| 交付 | 安装模块 | `hooks.json` 热更新 |
| 本仓库 | — | **只提供工具链 + DemoHook**，不提供某吧成品插件 |

---

## 6. 相关文档

- 总览（中文）：[README.zh-CN.md](../README.zh-CN.md)
- 流水线细则：[workflow.md](workflow.md)
- MCP 包说明：[../mcp/README.md](../mcp/README.md)
