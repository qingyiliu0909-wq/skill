# Timing Events 过滤规则

## 选择顺序

1. 从 FrameProvider 结果选时间窗口。
2. 用 `WhiteTracks` 选择 GameThread、RenderThread 等实际轨道。
3. 用 `BlackKeywords` 移除已经确认的噪声。
4. 只有已确认事件命名时才使用 `WhiteKeywords` 或 `WhiteEvents`。
5. 需要只看慢 Game/Rendering Frame 内事件时，增加分类帧耗时字段。

## 常见策略

区间下钻：

```json
{
  "StartTime": 50.5,
  "EndTime": 53.5,
  "WhiteTracks": ["GameThread"],
  "BlackKeywords": ["index [UnLua:", "newindex [UnLua:"]
}
```

慢 Game Frame 内事件：

```json
{
  "MinGameFrameDuration": 0.033,
  "WhiteTracks": ["GameThread"]
}
```

子系统聚焦：

```json
{
  "WhiteTracks": ["GameThread"],
  "WhiteKeywords": ["ReddotManager"]
}
```

## 注意

- 白名单会丢弃未匹配事件，未知分布时不要提前使用。
- 父节点关键字可能级联大量子节点，顶层目标应配合时间、深度或耗时限制。
- `duration` 及所有耗时过滤字段单位都是秒。
- 事件树只用于调用链分析，不用于推断真实帧率。
