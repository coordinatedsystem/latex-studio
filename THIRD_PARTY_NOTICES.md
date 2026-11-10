# 第三方组件与来源

| 组件 | 来源 | 许可说明 |
| --- | --- | --- |
| Monaco Editor | https://github.com/microsoft/monaco-editor | MIT，见 vendor/monaco/LICENSE |
| PDF.js | https://github.com/mozilla/pdf.js | Apache-2.0，见 vendor/pdfjs/LICENSE |
| Tectonic 0.17.0 | https://github.com/tectonic-typesetting/tectonic | MIT，见 assets/licenses/Tectonic-LICENSE.txt；依赖保留各自许可 |
| Python 3.13.17 | https://www.python.org/ | PSF，运行环境内含 LICENSE.txt |
| pypdf | https://pypi.org/project/pypdf/ | BSD-3-Clause，安装环境 dist-info 中保留许可 |
| pdfplumber / pdfminer.six | https://github.com/jsvine/pdfplumber | MIT，安装环境 dist-info 中保留许可 |
| pypdfium2 / PDFium | https://github.com/pypdfium2-team/pypdfium2 | Apache-2.0/BSD-3-Clause 及依赖许可，包内保留 notices |
| Pillow / cryptography 等 Python 依赖 | 各包 dist-info/METADATA | 原始许可证保留在运行环境中 |
| Inter | https://github.com/rsms/inter | SIL OFL 1.1，见 web/fonts/Inter-LICENSE.txt |
| Source Han Sans | https://github.com/adobe-fonts/source-han-sans | SIL OFL 1.1，见 web/fonts/SourceHanSans-LICENSE.txt |
| TeX 基础资源 | https://data1.fullyjustified.net/tlextras-2022.0r0.tar | 见 assets/licenses/ 中的 LPPL 与 TeX Live 许可；来自 Tectonic/TeX Live 资源分发，各文件保持原始许可与版权说明；可从原始分发取得完整源码与文档 |

编译器及基础资源在安装包中分发，源码仓库不包含个人 TeX 源文件。Windows 系统字体不打包。

安装包构建工具 Inno Setup：https://jrsoftware.org/ ，仅用于构建，不安装到最终用户环境。

## DeepSeek Harness 架构移植

Studio 助手的事件会话、稳定前缀投影、工具注册与未完成调用恢复，依据 DeepSeek Harness 的核心协议移植为 Python 实现；未嵌入完整 Cordis/Node 应用或第三方插件生态。来源：https://github.com/deepseek-ai/deepseek-harness ，固定版本 `fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`。重点对应 `packages/core/agent-loop/src/agent.ts`、`packages/core/session/src/repair.ts`、`packages/core/tools/src/batch.ts` 和 `packages/llm/llm-deepseek/src/adapter.ts`。保留 DeepSeek 2026 MIT 许可，见 `assets/licenses/DeepSeek-Harness-LICENSE.txt`。具体差异与验证见 `ASSISTANT_ARCHITECTURE.md`。
