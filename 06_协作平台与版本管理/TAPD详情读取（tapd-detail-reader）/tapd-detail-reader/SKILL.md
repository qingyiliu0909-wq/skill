---
name: tapd-detail-reader
description: 读取 TAPD “详细信息”页签内容的后台脚本指南。当用户要求读取 TAPD 需求/缺陷/任务详情页中的“详细信息”内容时使用此 skill。
---

# TAPD 详细信息读取 Skill

> **路径配置**：本文件中的路径占位符请先从 `.skill\CONFIG.md` 读取实际值。
> 本 Skill 位于 `读取tapd详细信息\tapd-detail-reader\`；下文提到的脚本均使用当前 Skill 目录下 `tools\` 中的文件。

## 目标

本 Skill 用于在**当前终端窗口**输出 TAPD 详情页中“详细信息”页签的文本内容。

实现要求已经内置在脚本中：

- 正常读取时使用 **Playwright headless** 后台浏览器，不在前台打开窗口。
- **不会默认自动安装 Chrome**。
- 首次使用时先**询问用户希望使用的浏览器**。
- 如果用户选择的浏览器未安装，则仅安装**用户选中的浏览器**。
- 如果读取时发现需要登录，则让用户执行一次登录流程。
- 登录成功后，将登录缓存保存在**项目根目录**下的 `.tapd-reader\` 中，后续优先复用该缓存。

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Setup-TapdReader.ps1` | 安装 Node 依赖，并确保用户选中的浏览器可被 Playwright 使用 |
| `{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Login-Tapd.ps1` | 启动可交互登录流程，并把登录态写入项目根目录缓存 |
| `{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Read-TapdDetail.ps1` | 后台读取 TAPD “详细信息”页签，并把文本直接输出到当前窗口 |
| `{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\scripts\*.js` | Playwright 实际实现 |
| `.tapd-reader\config.json` | 浏览器选择配置 |
| `.tapd-reader\storage-state-*.json` | 登录态缓存（按浏览器区分） |

---

## 浏览器选择规则

### 第一次使用

如果 `.tapd-reader\config.json` 不存在，先使用 `ask_user` 询问用户要使用哪个浏览器。

推荐顺序：

1. `Microsoft Edge`
2. `Google Chrome`
3. `Chromium`

映射关系如下：

| 用户选择 | 脚本参数 |
|----------|----------|
| Microsoft Edge | `edge` |
| Google Chrome | `chrome` |
| Chromium | `chromium` |

### 后续使用

后续优先读取 `.tapd-reader\config.json` 中的 `browser` 字段。

如果用户明确要求切换浏览器，再重新执行 `Setup-TapdReader.ps1 -Browser <browser>`。

---

## 推荐执行流程

### 1. 首次初始化或切换浏览器

先询问用户浏览器，然后执行：

```powershell
& "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Setup-TapdReader.ps1" -Browser edge
```

说明：

- 该脚本会安装 `{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\package.json` 中的 Node 依赖。
- 安装依赖时设置了 `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`，因此**不会因为安装 Playwright 而顺带下载 Chromium/Chrome**。
- 只有在用户选中的浏览器缺失时，才会安装对应浏览器。

### 2. 如果需要登录

当读取脚本提示登录缓存缺失或失效时，让用户执行：

```powershell
& "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Login-Tapd.ps1" -TapdUrl "https://www.tapd.cn/..."
```

可选地带浏览器参数：

```powershell
& "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Login-Tapd.ps1" -TapdUrl "https://www.tapd.cn/..." -Browser edge
```

说明：

- 该步骤会打开一个**可交互浏览器窗口**供用户完成登录。
- 用户登录完成并回到终端按回车后，脚本会把登录态写入 `.tapd-reader\storage-state-<browser>.json`。
- 正常读取流程本身仍然是后台 headless，不会在前台打开浏览器。

### 3. 后台读取“详细信息”

```powershell
& "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Read-TapdDetail.ps1" -TapdUrl "https://www.tapd.cn/..."
```

如果要临时覆盖浏览器：

```powershell
& "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Read-TapdDetail.ps1" -TapdUrl "https://www.tapd.cn/..." -Browser edge
```

脚本会：

1. 使用缓存登录态打开 TAPD 页面
2. 在后台点击或激活“详细信息”页签
3. 抽取该页签中的可见文本
4. 直接输出到当前终端窗口

---

## 实际使用时的行为规范

当用户要求“读取 TAPD 详细信息”时，按以下规则执行：

1. 如果用户没有给 URL，先向用户索要目标 TAPD 详情页 URL。
2. 检查 `.tapd-reader\config.json` 是否存在：
   - 不存在：先询问浏览器，再执行初始化脚本。
   - 存在：直接使用已保存浏览器。
3. 调用读取脚本：
   ```powershell
   & "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Read-TapdDetail.ps1" -TapdUrl "<URL>"
   ```
4. 如果脚本报错提示需要登录，则提示用户执行登录脚本并完成登录：
   ```powershell
   & "{SKILLS_ROOT}\读取tapd详细信息\tapd-detail-reader\tools\Login-Tapd.ps1" -TapdUrl "<URL>"
   ```
5. 用户完成登录后，重新执行读取脚本。
6. 将脚本输出的“详细信息”内容直接返回给用户；默认不要额外加工，除非用户要求总结或结构化整理。

---

## 注意事项

- 不要在读取步骤中切换到前台可见浏览器；读取应保持 headless。
- 不要默认安装 Chrome；只有在用户明确选了 `Google Chrome` 且本机缺失时才安装。
- 缓存目录位于项目根目录 `.tapd-reader\`，不要改存到临时目录。
- 如果登录缓存失效，优先走 `Login-Tapd.ps1` 刷新缓存，不要手工删改缓存文件。
- TAPD 页面 DOM 结构可能变化；如果读取失败，优先复用现有脚本修正选择器，不要新建第二套实现。
