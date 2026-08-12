---
name: ue-build-debug
description: EM Unreal Engine 项目的构建、调试与结构导航指南。当被要求构建项目、修复编译错误或了解 UE 项目结构时使用此 skill。
---

# EM Unreal Engine 项目 — 构建与调试指南

## 项目结构

- `Source/EM/` — 主游戏模块（C++）
- `Source/EMEditor/` — 编辑器模块
- `Source/EMServer/` — 独立服务器目标
- `Plugins/` — 项目插件
- `Config/` — INI 配置文件
- `Content/Script/` — 项目lua脚本
- `Tools/` — 附加工具
- `AutoBuild.bat` — 完整自动构建脚本

## 构建目标

在 `Source/*.Target.cs` 中定义：
- `EM` — 游戏客户端
- `EMEditor` — 编辑器构建
- `EMServer` — 独立服务器

## 常见操作

### 构建项目
从项目根目录运行 `AutoBuild.bat`，或直接使用 Unreal Build Tool (UBT)：
```
Engine\Build\BatchFiles\Build.bat EM Win64 Development "path\to\EM.uproject"
```

### 在编辑器中打开
双击 `EM.uproject`，或通过 Unreal Engine 启动器打开。

### 修复编译错误
1. 查看 `Saved\Logs\` 获取详细日志。
2. 查看项目根目录下的 `output.log` 了解最近的构建输出。
3. 中间构建产物位于 `Intermediate\Build\` — 删除该目录可强制全量重新编译。

### 服务器操作
- `server_init.bat` — 初始化服务器
- `server_restart.bat` — 重启服务器
- `start_server.bat` — 启动服务器
- `server_update_restart.bat` — 更新并重启服务器

## 注意事项
- 这是一个 C++ UE 项目，修改 `.h`/`.cpp` 文件后需要重新构建。
- 解决方案文件为 `EM.sln`，可在 Visual Studio 或 Rider 中打开。
- `Script/` 下的 Python 脚本使用 UE 内置的 Python 解释器运行。
