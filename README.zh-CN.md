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
- 工作流细则：[docs/workflow.md](docs/workflow.md)
- MCP 说明：[mcp/README.md](mcp/README.md)

## 许可证

Apache License 2.0 — 见 [LICENSE](LICENSE)。
