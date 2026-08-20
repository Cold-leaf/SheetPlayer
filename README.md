# SheetPlayer

谱音同步打点播放器 —— 单 HTML 文件实现：在五线谱 PDF 上标记小节，按音频打时间点，播放时谱面跟随高亮滚动。可安装成 PWA（独立全屏、离线可用、数据持久）。

## 使用

托管后（GitHub Pages）用浏览器打开 `https://<你的用户名>.github.io/SheetPlayer/`，建议「添加到主屏幕 / 安装应用」变成独立应用。本地也可以双击 `player.html`（file:// 下 PWA 不生效，其余功能一样）。

1. 启动进入「曲目库」：「＋ 导入谱子」选一个 PDF（一个曲目 = 1 个 PDF + N 个音频变体 + 1 份标注）。
2. 「标小节」模式：点谱面标记每个小节的位置。
3. 「音频变体」下拉：给曲目挂多个音频（不同声部/伴奏），随时切换，标注不动。
4. 「打时间」模式：空格键给当前小节打时间点（或点竖线）。
5. 「播放」模式：谱面随播放高亮滚动。

其他能力：自动生成时间轴（按拍号/播放顺序）、小节线吸附、频谱与起音吸附、多小节休止、横向铺开、练习循环、触屏适配、双指/触控板缩放、JSON 导入导出、自动存档。

## 部署到 GitHub Pages

1. 仓库 Settings → Pages → Source 选 **Deploy from a branch** → 分支 `main`、目录 `/ (root)` → Save。
2. 等一两分钟，站点地址是 `https://<用户名>.github.io/SheetPlayer/`。
3. 仓库须公开（GitHub Pages 免费账户的硬要求）；部署的只是播放器空壳，谱子/音频永不上传，留在本地 IndexedDB。

## 开发

- 源码即 `player.html` 单文件（CSS + JS 内联）。PWA 外壳：`manifest.json` + `sw.js` + `icon-*.png` + `index.html`（站点根重定向）；`lib/` 是本地化的 pdf.js（3.11.174），离线也能渲染谱子。
- 发布后改动了内容记得 bump `sw.js` 里的 `VER`，否则旧缓存不清、用户拿不到更新（页面走网络优先，一般能自动更新，但 lib 走缓存优先）。
- 测试在 `tests/`：
  - `tests/t*.js`：纯逻辑测试。t9 直接从 player.html 提取 `/*PURE*/` 块测真实代码；其余为手工拷贝的函数快照。
  - `tests/pw_*.py`：Playwright 浏览器端到端测试（`?direct=1` 参数让它们跳过曲目库、走传统 localStorage 路径；库功能由 `pw_lib*.py` / `pw_migrate.py` / `pw_idbnull.py` 覆盖）。
  - 一键跑全套：`bash tests/run-tests.sh`（grep 输出中的 FAIL，任一失败 exit 1）。
- 测试里的 PDF/音频路径指向本机 `data/assets/`，换机器需改 `ROOT`。

## 数据说明

- **曲目库**（IndexedDB，库名 `sheetplayer`）：标注按 PDF **内容哈希**（前 1MB SHA-256）关联，文件名只做显示；PDF/音频文件副本、频谱分析缓存也在库里。换文件名不丢标注；同一内容重复导入自动去重。
- **降级**：IndexedDB 不可用（如隐私模式）自动退回 localStorage 按文件名存档；localStorage 也不可用则退内存 + 一次性警告（记得用「导出JSON」）。
- **老数据迁移**：旧版 localStorage 存档（`player:<文件名>` 键）启动时自动扫进曲目库，等对应 PDF 打开、哈希解析完成后再清老键。
- **跨设备同步**：曲目库界面「导出全部标注 / 导入全部标注」打包所有曲目的标注 JSON（只同步标注，不搬文件——对端把 PDF 导进库后按哈希自动对上）。
- 单曲「导出JSON / 导入JSON」保留可用，导出带 `pdfHash` 字段用于校验谱子对不对。
