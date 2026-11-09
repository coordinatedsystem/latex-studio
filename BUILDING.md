# 构建与发布

1. 修改 `version.json`（可运行 `tools/set_version.py`），补充 `CHANGELOG.md`。
2. 从 Python 官方下载 Windows x64 嵌入式发行版到专用 `payload/python/`。当前版本为 3.13.17。保留原始许可。
3. `python313._pth` 包含 `python313.zip`、`.`、`Lib/site-packages`、`../app` 和 `import site`。
4. 把 `requirements-lock.txt` 中的 Windows CPython 3.13 二进制依赖安装到 `payload/python/Lib/site-packages`。不要复制个人 Python 环境、pip 配置或用户目录。
5. 获取 Tectonic 0.17.0 官方 Windows x64 发行版和匹配的基础资源索引。当前发行包的编译器 SHA256 可见运行目录的 `release.json`。
6. 使用 Inno Setup 6.7.4 的 ISCC 编译。示例：

```powershell
python -B tools/build_release.py `
  --runtime D:\BuildInputs\tectonic `
  --tex-cache D:\BuildInputs\tex-cache `
  --payload D:\BuildInputs\payload `
  --iscc "C:\BuildTools\InnoSetup\ISCC.exe"
```

构建脚本通过白名单复制应用文件，仅复制索引中存在且大小一致的 TeX 资源，不复制本机配置、项目、历史或 format 缓存。发布前检查 `build-manifest.json`。

应用复制后会逐文件比较源码与载荷的 SHA256，缺失、变化或额外残留文件都会阻止打包。尤其新增 `studio_*.py`、前端脚本及样式时，无需手工维护复制清单。构建目录应专用于发布，不放入安装后的本机设置；Python 运行环境放在 `payload/python/`。

运行 `python -B tools/audit_release.py .`，在独立目录实际安装、离线编译、生成 PDF 页面图像并测试升级保留文档。完成后提交源码、`distribution/` 与 `updates/latest.json`，打 `v版本号` 标签并推送。

本版本安装包小于 100 MiB，暂随仓库分发；后续若使用 GitHub Releases，需要相应维护发布流程和只读下载接口，不能把发布写入凭据内置进应用。

仓库不包含安装包签名私钥或账户凭据。Windows 安装包目前未签名；构建工具本身从官方来源获取并验证数字签名。
