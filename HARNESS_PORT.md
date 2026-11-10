# DeepSeek Harness 核心架构移植

来源：[DeepSeek 官方仓库](https://github.com/deepseek-ai/deepseek-harness)，固定提交 `fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`。使用 MIT 许可，保留原版权与许可文本。

| 官方实现 | Studio 中的落点 | 实际行为 |
| --- | --- | --- |
| `core/agent-loop/src/agent.ts` | 文档任务驱动与模型上下文 | 区分 turn/step，准备后冻结请求，按实际进展继续执行 |
| `core/session` 的事件日志和消息投影 | `studio_assistant_session.py` | 追加事件、还原模型请求，继续时保留稳定前缀 |
| `core/session/src/repair.ts` 的 ToolCallRecovery | 中断调用恢复 | 区分尚未派发与结果未知，不盲目重做编辑 |
| `core/tools` 注册、策略和调用结果 | `studio_assistant_tools.py` | 工具描述和执行权限来自同一份注册；支持注销；修改与编译顺序执行 |
| `llm/llm-deepseek/src/adapter.ts` 的准备/请求生命周期 | `studio_assistant_provider.py` | 单次请求冻结模型、参数、消息与工具；暂时故障重试不重复工具 |
| 稳定消息前缀与按需消息投影 | 上下文投影和压缩 | 平时只追加；到阈值再本地压缩，不每轮移动或重建旧结果 |

这次移植保留 Studio 的 Python 安装环境、DeepSeek Chat Completions 兼容接口、LaTeX 编译器和候选确认/撤销机制。没有引入完整 Node/Cordis 应用、外部插件市场、任意终端执行、DSH 的全部 Messages 扩展或子智能体功能。工具当前保持串行；注册信息已具备独占标记，但不声称已实现官方的并行调度器。

真实服务验证仅使用合成文件。15 处讲义相关说明的一次任务：5 次请求、17112 token，其中输入缓存命中 13568 token；修改、编译、原稿保护和精确撤销通过。相同场景上一版实测为 6 次、21841 token，但模型执行有波动，这不是所有任务的节省承诺。切回 Chat 的讨论仅 1 次请求，无修改和编译。

完整技术说明见 `ASSISTANT_ARCHITECTURE.md`，验证记录见 `RELEASE_VALIDATION.md`。
