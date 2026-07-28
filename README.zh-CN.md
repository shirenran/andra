# Andra

[English](README.md) | **中文**

**Andra** = 可热更新的 **LSPosed Hook 运行时** + **桌面端逆向 MCP**。

在电脑上写好 `hooks.json`，用 adb 部署进手机，注入到宿主 App —— 不必每次小改都重编 Xposed 模块。

```text
load_apk → 搜索 / 反编译 → write_plugin → deploy_plugin → verify_plugin
```

| 层级 | 路径 | 说明 |
|------|------|------|
| **Runtime** | `runtime/` | Android 应用 `dev.andra.runtime`（LSPosed 模块 + 状态页） |
| **MCP / CLI** | `mcp/` | Python MCP 服务 + 命令行（DEX 检索、jadx、部署、验证） |
| **文档** | `docs/` | 完整流水线与防卡死规则 |

## 它能干什么？

传统做法：每次想试一个 Hook，都要改 Java → 编译 APK → 安装 → 重启作用域。  
**Andra 的做法：改几个 JSON，推到手机，强停宿主即可生效。**

| 场景 | 你怎么做 | 结果 |
|------|----------|------|
| 看某个方法有没有被调用、参数是什么 | `kind: log` | 中文 I/E 日志写到宿主 media 目录 |
| 临时关掉付费/试用判断（自有 App 调试） | `kind: replace` + `return_value` | 方法直接返回你指定的值 |
| 方法跑完后再看返回值 | `kind: after` + `log_result` | 不改逻辑，只观察 |
| 配合 AI 逆向 | MCP：`load_apk` → 搜字符串 → `write_plugin` → `deploy` | 从 APK 定位到可部署插件一条龙 |

适合：自有 / 授权 App 的调试、自动化验证、快速验证 Hook 点。  
不适合：当成「一键破解某某商业 App」的成品仓库（本仓库也不附带这类插件）。

## 使用示例

### 示例 1：5 分钟跑通 Demo（系统设置）

目标：打开「设置」时，在日志里看到 `Activity.onResume` 被调用。

仓库里已有插件：[`mcp/workspace/plugins/DemoHook/`](mcp/workspace/plugins/DemoHook/)

```json
// hooks.json（已写好）
[
  {
    "class_name": "android.app.Activity",
    "method_name": "onResume",
    "kind": "log",
    "note": "smoke"
  }
]
```

```bash
# 0. 手机：安装 Andra APK，LSPosed 启用，作用域勾选「设置」com.android.settings
# 1. 电脑部署
cd mcp && uv sync
uv run python -m andra.cli deploy DemoHook --package com.android.settings

# 2. 强停并打开设置，再读日志
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
# 或
uv run python -m andra.cli read-log --host com.android.settings --plugin DemoHook --level IE
```

成功时大致会看到类似：

```text
07-29 12:00:01.234  I  [DemoHook]  Hook 就绪 1/1
07-29 12:00:02.100  D  [DemoHook]  调用 android.app.Activity.onResume 参数=...
```

（UI / `read-log` 默认偏 I/E；完整细节在 `andra.log` 文件里。）

### 示例 2：强制某个方法返回 true（自有 App）

假设你自己的应用包名是 `com.mycompany.demo`，有个开关：

```java
// com.mycompany.demo.feature.FeatureFlags
public boolean isPremiumUnlocked() { return false; }
```

本地调试时想永远当已解锁，不必改业务代码重装：

**1. 写插件目录** `mcp/workspace/plugins/UnlockPremium/`

`plugin.json`：

```json
{
  "id": "UnlockPremium",
  "name": "UnlockPremium",
  "version": "1.0.0",
  "desc": "本地调试：强制 premium 开关",
  "targetPackage": "com.mycompany.demo",
  "hooksFile": "hooks.json"
}
```

`hooks.json`：

```json
[
  {
    "class_name": "com.mycompany.demo.feature.FeatureFlags",
    "method_name": "isPremiumUnlocked",
    "kind": "replace",
    "return_value": "true",
    "note": "local debug only"
  }
]
```

**2. LSPosed 作用域勾选 `com.mycompany.demo`（不要勾系统框架）**

**3. 部署并验证**

```bash
cd mcp
uv run python -m andra.cli deploy UnlockPremium --package com.mycompany.demo
adb shell am force-stop com.mycompany.demo
# 打开 App，点会走 isPremiumUnlocked 的界面
uv run python -m andra.cli read-log --host com.mycompany.demo --plugin UnlockPremium --level IE
```

改返回值？只改 `hooks.json` 再 `deploy` 一次，**不用重编 Andra 或宿主 APK**。

### 示例 3：MCP 实战 — 某吧去广告（AI 一条龙）

这是 Andra **最典型**的用法：对 AI 说目标，MCP 自动「搜 APK → 写插件 → 部署」。

> 类名 / 包名为教学占位（`com.example.forum`）。真实某吧以你本机 APK 为准。  
> 仓库**不附带**商业 App 成品插件，只教工作流。更细的逐步说明见 **[docs/mcp-usage.zh-CN.md](docs/mcp-usage.zh-CN.md)**。

#### 3.1 接入 MCP

```bash
cd mcp && uv sync
```

客户端配置（路径改成你的仓库绝对路径）：

```toml
[mcp_servers.andra]
command = "uv"
args = ["run", "--directory", "/path/to/andra/mcp", "python", "-m", "andra.server"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 600
```

手机：Andra 已安装；LSPosed 作用域**只勾某吧**；`adb devices` 在线。

#### 3.2 对 AI 怎么说

```text
用 andra MCP 给某吧去信息流广告。
APK：/path/to/forum.apk
包名：com.example.forum
流程：load_apk → search_strings → find_usage → decompile_method
     → write_plugin → deploy_plugin → verify_plugin
约束：find_method 必须带 in_class；不要空等 logcat；hooks 用 replace 关广告开关。
```

#### 3.3 AI 实际会调的工具（顺序）

```text
① load_apk(path=".../forum.apk")
② search_strings("广告") / search_strings("showFeedAd") / search_strings("/c/ad/")
③ find_usage(string="showFeedAd")          # 谁引用了这串
④ decompile_method(class=FeedAdManager, method=shouldShowAd)
⑤ write_plugin(name="ForumNoAd", target_package="com.example.forum", hooks=[...])
⑥ deploy_plugin(name="ForumNoAd", target_package="com.example.forum")
⑦ verify_plugin / read_andra_log           # 看 Hook 就绪、广告是否还在
```

#### 3.4 最终插件长这样

`hooks.json` 示意（方法名需用你反编译结果替换）：

```json
[
  {
    "class_name": "com.example.forum.ad.FeedAdManager",
    "method_name": "shouldShowAd",
    "kind": "replace",
    "return_value": "false",
    "note": "信息流广告开关"
  },
  {
    "class_name": "com.example.forum.ad.SplashAdHelper",
    "method_name": "needSplash",
    "kind": "replace",
    "return_value": "false",
    "note": "开屏广告开关"
  }
]
```

部署路径：

```text
/sdcard/Android/media/com.example.forum/Andra/plugins/ForumNoAd/
```

强停某吧 → 再打开 → 滑信息流。不好使就对 `loadAd` 先 `kind: log` 看调用栈，或 `find_caller` 换钩子，**只改 JSON 再 deploy**，不用重编模块。

#### 3.5 工具优先级（防卡死）

| 推荐 | 慎用 |
|------|------|
| `search_strings` → `find_usage` → `find_caller` | 无 `in_class` 的 `find_method` 全表扫描 |
| `decompile_method`（候选很少时） | 大包一上来 `decompile_all` |
| `verify_plugin` / `read_andra_log` | 长时间 live `capture_logcat` |

### 和「手写 Xposed 模块」对比

| | 手写 Xposed 模块 | Andra 插件 |
|--|------------------|------------|
| 改一处 Hook | 改 Java → 编译 → 安装模块 | 改 `hooks.json` → deploy |
| 多宿主 | 常在代码里写死包名 | 每个插件一个 `targetPackage` |
| 和 AI 配合 | 要让模型吐整模块工程 | 模型只需产出 JSON hook 列表 |
| 调试反馈 | 主要靠 logcat | 宿主 media 下中文 I/E 文件日志 + `verify` |

## 环境要求

- 已 Root 的 Android 手机，并安装 **LSPosed**（或兼容框架）
- 电脑端 `adb`
- 可选：[jadx](https://github.com/skylot/jadx)、[uv](https://github.com/astral-sh/uv)、JDK 17+

## 快速开始

### 1. 编译并安装 Runtime

```bash
# 在仓库根目录（需 Android SDK；在 local.properties 中设置 sdk.dir）
./gradlew :runtime:assembleRelease
adb install -r runtime/build/outputs/apk/release/runtime-release.apk
```

在 LSPosed 中：

1. 启用 **Andra**
2. 作用域 = **只勾宿主 App**（不要勾系统框架）
3. 修改作用域后强停宿主 App 再打开

### 2. 运行桌面 MCP / CLI

```bash
cd mcp
uv sync
uv run python -m andra.cli --help
uv run python -m andra.server   # MCP stdio
```

### 3. 示例插件

示例在 `mcp/workspace/plugins/DemoHook/`（对 `com.android.settings` 的 `Activity.onResume` 打 log）。

```bash
cd mcp
uv run python -m andra.cli deploy DemoHook --package com.android.settings
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
```

## 插件目录结构

```text
plugin.json     # id、targetPackage、version 等
hooks.json      # 运行时真正执行的内容
main.bsh        # 文档 / 预留 BeanShell（当前非必须）
INSTALL.md      # 人工说明
.enabled        # 在设备上 touch 此文件以启用
```

**手机路径（推荐）：**

```text
/sdcard/Android/media/<宿主包名>/Andra/plugins/<插件名>/
```

日志：

```text
/sdcard/Android/media/<宿主包名>/Andra/logs/andra.log
```

不要只推到 `/sdcard/Android/data/dev.andra.runtime/...`：现代 Android 下宿主读不到别的应用的 `Android/data`。

## hooks.json

```json
[
  {
    "class_name": "com.example.Vip",
    "method_name": "isVip",
    "kind": "replace",
    "return_value": "true",
    "note": "gate"
  }
]
```

| `kind` | 行为 |
|--------|------|
| `log` | 记录参数 / 返回值 |
| `before` | 调用前执行；可选 `return_value` 直接短路 |
| `after` | 调用后执行；可选覆盖 `return_value` |
| `replace` | 用 `return_value` 设置返回结果 |

可选 note 标记：`log_result`（额外打印返回值）。

## MCP 客户端配置示例

```toml
[mcp_servers.andra]
command = "uv"
args = ["run", "--directory", "/path/to/andra/mcp", "python", "-m", "andra.server"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 600
```

## 无线 ADB

请使用真实 Wi-Fi IPv4。**不要**用 VPN 虚拟地址（如 `172.19.*`）。

```bash
uv run python -m andra.cli connect 192.168.x.x:<PORT>
```

环境变量：`ANDRA_ADB`、`ANDRA_WIFI_HOST`、`ANDRA_WORKSPACE`、`ADB_BIN`、`JADX_BIN`。

## LSPosed 作用域

| 勾选 | 需要？ |
|------|--------|
| 宿主 App（如 `com.android.settings`） | **必须** |
| 系统框架 `system` | **不需要**（普通 App hook） |
| Andra 自身 `dev.andra.runtime` | 一般不需要 |

Andra 在**宿主进程**内读 plugins 并 hook，不依赖注入 `system_server`。

## 仓库结构

```text
andra/
  runtime/          # LSPosed 模块（Gradle :runtime）
  mcp/              # Python 包 andra-mcp
  docs/workflow.md  # 逆向 → 部署完整流水线
  LICENSE           # Apache-2.0
  README.md         # English
  README.zh-CN.md   # 中文
```

## 开源范围

- **包含：** 通用 hook 引擎、状态页 UI、MCP 逆向工具、DemoHook 示例
- **不包含：** 第三方 APK、反编译产物、针对具体商业 App 的私有自动化插件

请仅在你拥有或已获授权调试的应用上使用。

## 更多文档

- 英文总览：[README.md](README.md)
- **MCP 使用（某吧去广告逐步）**：[docs/mcp-usage.zh-CN.md](docs/mcp-usage.zh-CN.md)
- 工作流细则：[docs/workflow.md](docs/workflow.md)
- MCP 包说明：[mcp/README.md](mcp/README.md)

## 许可证

Apache License 2.0 — 见 [LICENSE](LICENSE)。
