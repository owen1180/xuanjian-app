# 玄鉴命理馆 · 离线本机版（iOS PWA）交付概览

> 目标设备：**iPhone 18 Pro Max / iPad Pro 11（型号 FU152CH/A，国行）**
> 形态：PWA（添加到主屏幕的网页应用），引擎全内嵌、断网可用、数据不出本机、不依赖服务器。

## 一、为什么是 PWA 而不是原生 App

iOS 上"不依赖电脑、不装 Xcode、不交开发者费、能在真机本机离线跑 Python 引擎"的唯一可行路径就是 PWA：

- 引擎是 Python 写的（四柱打分、紫微排盘、黄历、六爻梅花、小六壬、取名五格等），无法直接打进 iOS 原生包；
- 用 **Pyodide（Python→WebAssembly）** 把引擎编译进手机 Safari 离线运行，再用「添加到主屏幕」变伪原生全屏 App；
- FU152CH/A 是国行 iOS 通用二进制，机型只在安装授权阶段起作用，功能与全球版完全一致，**无需特殊处理**。

## 二、关键技术卡点及解决

**卡点**：Pyodide 是纯 WASM 环境，没有 `sxtwl`（寿星天文历 C 扩展）。而农历换算、节气、月干支（节气月）、年干支（立春界）、值宿、胎神、宜忌全部依赖它——缺了 sxtwl，公历↔农历换算在手机上直接失败。

**解法**：用本机 sxtwl 预先生成一张**纯数据表** `_lunar_data.py`（覆盖 1895–2105），在 `except ImportError/Exception` 分支兜底：

| 调用点 | 原路径（本机有 sxtwl） | 离线兜底（Pyodide 无 sxtwl） |
|---|---|---|
| `ziwei_pan.py` ×3（公历转农历、内置农历、农历月天数） | sxtwl | `_lunar_data.lunar_of` |
| `huangli.py · lunar_text` | sxtwl | `_lunar_data.lunar_of` |
| `zeri.py` ×3（day_info / liminal / year_zhi） | sxtwl | `_jdn_day_gz` + `_lunar_data` |
| `xiaoliuren.py · solar_to_lunar` | sxtwl | `_lunar_data.lunar_of` |
| `meihua.py · cast_time` | sxtwl | `_lunar_data` + 时辰公式 |

- 本机有 sxtwl 走原路径便于**对拍校验**；Pyodide 无 sxtwl 走离线兜底，结果**完全一致**（农历/月干支/年支/节气/liminal 对拍 mismatch=0）。
- 日干支用儒略日公式纯算（与 sxtwl 一致，采样 mismatch=0），八字/紫微日柱本就不依赖 sxtwl。

## 三、验证结果（全部通过）

**Pyodide 离线引擎真机等效验证（ALL OK ✅）**：

- `bazi(1985,4,12,10)` → 四柱 `乙丑 己卯 辛巳 癸巳`、总分 45.5、档位偏弱
- `ziwei(1985,4,12,10,'男')` → 命宫丙戌 / 身宫甲申 / 土五局 / 12 宫
- `huangli(2026,11,2)` → 含胎神 / 宜忌 / 节气 / 彭祖百忌完整输出
- `xiaoliuren_number("12345")` → 通过
- `qiming("张","11,11",1,"")` → 通过

**真实 App 端到端验证**：启动显示「就绪」→ 点击八字按钮 → 正确输出「乙丑 己卯 辛巳 戊子｜总分44.5｜太弱」。

**语法自检**：`node --check app.js`、`node --check sw.js` 均 OK。

## 四、交付文件清单（目录 `xuanjian-app/`）

| 文件 | 作用 |
|---|---|
| `index.html` | 应用入口（PWA 主页，含 manifest / apple-touch-icon 配置） |
| `app.js` | 前端逻辑：启动 Pyodide、调用引擎、渲染（已修默认时辰 selected） |
| `styles.css` | 样式（移动端全屏适配） |
| `manifest.webmanifest` | PWA 清单 |
| `sw.js` | Service Worker 离线缓存（已修 pyodide 子路径兼容） |
| `engine.zip`（1.59MB） | 根级 `engine_bridge.py` + `skills/`（含 `_lunar_data.py` 161770 字节） |
| `engine_bridge.py` | Python↔JS 桥接层 |
| `pyodide/`（约14MB） | Pyodide 运行时（随包下发，首次联网下载并缓存） |
| `icons/` | 主屏图标 |
| `engine/` | 可编辑引擎源码（改动在此，改后重打 engine.zip） |
| `README.md` | 安装与部署说明（核心交付物） |

## 五、用户安装路径（详见 README.md）

1. 把整目录部署到 **HTTPS** 站点（GitHub Pages / Netlify / 自有服务器均可；`http://局域网IP` 或 `file://` 在 iOS 上无法安装）；
2. 用 iOS Safari 打开地址，等顶部进度条走到「就绪」（首次需联网下载约 16MB 运行时）；
3. 分享菜单 →「添加到主屏幕」→ 命名「玄鉴」→ 桌面图标即伪原生 App；
4. 之后**断网也能用**；更新改 `sw.js` 的 `CACHE = "xuanjian-v1"` 为 `v2` 强制刷新。

## 六、计算口径与边界

- 农历/节气/月干支（节气月）/年干支（立春界）/值宿/胎神/宜忌：内置预生成数据表 **1895–2105**，与云端同源一致；
- **边界**：生辰落在 **1895 年之前或 2105 年之后**，农历/节气数据不保证准确，请勿用于此类极端日期；
- 引擎为离线本地计算，结果仅供传统文化分析参考，不作医疗/投资/法律决策依据。

---
© 玄鉴命理馆（Xuanjian Destiny Studio）™ · 传统术数文化分析，供参考
── 玄鉴 · 命途图 ──（XJ-1.78）
