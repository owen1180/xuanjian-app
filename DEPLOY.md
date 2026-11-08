# 部署手册 · 把玄鉴离线版发布成 HTTPS 站点（无需自己的服务器）

本目录已是一个完整、可直接发布的静态站点。下面是两种**免费、自动带 HTTPS** 的发布方式，任选其一。

> 关键前提：iOS Safari 的「添加到主屏幕」+ 离线缓存**强制要求 HTTPS**（本机 localhost 除外）。
> 本应用所有资源路径都用相对路径，因此部署在「子路径」（如 `用户名.github.io/仓库名/`）也能正常工作。

---

## 方式 A：GitHub Pages（推荐，最稳，免费 HTTPS）

适合：有（或愿意注册一个）免费 GitHub 账号的人。

### 第 1 步：在 github.com 新建一个空仓库
- 进入 https://github.com/new
- 仓库名随便取，例如 `xuanjian-app`
- **不要**勾选「Initialize with README / .gitignore」——保持空仓库
- 点 Create repository

### 第 2 步：在本目录执行三条命令（把 `你的用户名` 换成实际账号）
```bash
git remote add origin https://github.com/你的用户名/xuanjian-app.git
git branch -M main
git push -u origin main
```

### 第 3 步：开启 Pages
- 进入仓库 **Settings → Pages**
- Source 选 **Deploy from a branch**，Branch 选 **main**，目录选 **/root**
- 点 Save
- 约 1–2 分钟后，访问 `https://你的用户名.github.io/xuanjian-app/` 即可

### 第 4 步：在 iPhone / iPad 上安装
1. 用 Safari 打开上面的地址
2. 等顶部进度条走到「就绪」（首次需联网下载约 16MB 运行时）
3. 点底部「分享」→ 下滑找到「添加到主屏幕」→ 命名为「玄鉴」
4. 桌面图标即伪原生 App，**之后断网也能用**

### 更新引擎后
改完 `engine/` 源码后重打 `engine.zip`，然后把 `sw.js` 里的
`const CACHE = "xuanjian-v1";` 改成 `xuanjian-v2`（或更高），再 `git push`，
手机上用 Safari 重新打开一次地址即可刷新缓存。

---

## 方式 B：Netlify Drop（零 git、零命令行、30 秒搞定）

适合：完全不想碰命令行的人。

1. 浏览器打开 https://app.netlify.com/drop
2. 把本 `xuanjian-app` 文件夹**整个拖进去**
3. 数秒后 Netlify 给你一个 `https://随机名.netlify.app` 的 HTTPS 地址
4. 用 iPhone Safari 打开该地址 → 等「就绪」→ 添加到主屏幕

> 注意：Netlify Drop 默认拖入的文件夹即站点根目录，必须确保 `index.html` 在根。
> 拖的时候请拖「xuanjian-app 这个文件夹本身」，不要只拖里面的文件。
> 免费 Drop 站点若长期无人访问可能被回收；要长期稳定用方式 A。

---

## 其他方式（已有自有服务器 / VPS 时）

把本目录整个上传到任意支持 HTTPS 的静态空间即可（Nginx / Caddy / 对象存储+CDN 等）。
若用 Caddy，一行 `tls` 自动申请免费证书；若用 Nginx，配好证书并把本目录设为 root。
确保 `index.html` 在站点根，且整站走 HTTPS。

---

## 验证清单（发布后自检）
- [ ] 手机 Safari 打开地址，能看到「玄鉴」启动页
- [ ] 进度条走到「就绪」，无报错
- [ ] 点「八字」能算出结果（如 1985-04-12 10 时 → 乙丑 己卯 辛巳 戊子）
- [ ] 分享菜单里有「添加到主屏幕」
- [ ] 安装后断 Wi-Fi 仍能打开并使用

## 边界提醒
- 生辰落在 **1895 年之前或 2105 年之后**，农历/节气数据不保证准确，请勿用于极端日期。
- 引擎为离线本地计算，结果仅供传统文化分析参考，不作医疗/投资/法律决策依据。
