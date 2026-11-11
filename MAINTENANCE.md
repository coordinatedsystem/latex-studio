# 项目维护

## 当前发布与历史安装包

当前分支的 `distribution/` 仅保留 `updates/latest.json` 对应的最新版安装包和校验文件。旧版本仍保存在各自 Git 标签的 `distribution/` 中，所有提交和标签均保留。维护不修改已安装应用版本，不改动应用的文档、设置、附件、会话和候选预览。

如需下载旧版本，可打开相应标签，例如 [v1.7.0 安装包目录](https://github.com/coordinatedsystem/latex-studio/tree/v1.7.0/distribution)。开发者也可使用 Git 恢复指定文件，避免通过 PowerShell 文本重定向导出二进制：

```powershell
git restore --source=v1.7.0 --worktree -- distribution/LaTeX-Studio-1.7.0-win64-Setup.exe
```

## 日常检查

```powershell
python -B tools/maintain_workspace.py
python -B tools/audit_release.py .
git status --short
```

维护工具默认只生成报告并验证最新安装包的大小和 SHA-256，不删除文件、不调用模型服务。安装工作区内的报告保存在 `release-verification/`。

确认当前应用空闲、新版安装包和已安装应用完整后，可执行：

```powershell
python -B tools/maintain_workspace.py --clean
```

清理有明确范围：

- 只移除与对应版本标签内容完全一致、没有本地修改的旧安装包，最新版始终保留。
- 只处理工具明确列出的过期开发目录，不使用模糊路径扫描清理缓存；重复参考源码必须无本地改动、且与保留的参考版本一致。
- 旧测试环境中的 `data/`、`projects/` 及独立测试安装的同名目录，先压缩到 `archive/maintenance-时间/` 并逐文件核对 SHA-256，再移除可再生成的运行和构建资源。
- 当前 `data/`、`projects/` 在清理前后逐文件校验；字体、Tectonic 宏包、助手候选预览、公共构建资源和固定版 Harness 参考源码保留。
- 缓存路径必须直接位于工作区 `cache/` 下；拒绝符号链接和目录连接。活动任务或仍运行的临时开发服务会阻止相应清理。

## Git 存储维护

本轮执行了普通 Git 对象压缩。保留未引用对象和所有 reflog，不执行历史改写、强制推送或立即清除对象。Git 历史仍包含历代安装包，因此它占据的大部分空间会继续保留。

开发者可在没有其他 Git 写操作时重复执行保守压缩：

```powershell
git -c gc.pruneExpire=never -c gc.reflogExpire=never -c gc.reflogExpireUnreachable=never -c pack.threads=2 -c pack.windowMemory=128m gc
```

2026-11-11 维护结果：清理 14 个旧安装包副本、4 个过期开发目录；50 个测试状态文件已备份并校验。清理步骤释放约 1.49 GiB，另有 Git 压缩约 57 MiB。工作目录约从 3.91 GiB 降至 2.36 GiB。699 个已安装应用文件校验通过，当前用户数据校验未变化。
