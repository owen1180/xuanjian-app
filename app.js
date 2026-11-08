/* 玄鉴命理馆 · 离线 PWA 前端
   流程：加载 Pyodide → 取 engine.zip 解压进虚拟文件系统 → import engine_bridge → 调用。
   全部计算在本机（iPhone/iPad）完成，不联网、不传云。 */

let pyodide = null;

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function setBoot(pct, msg) {
  $("#bootBar").style.width = pct + "%";
  if (msg) $("#bootMsg").textContent = msg;
}

/* ---------- 启动引擎 ---------- */
async function boot() {
  try {
    setBoot(10, "加载 Python 运行时…");
    pyodide = await loadPyodide({ indexURL: "./pyodide/" });
    setBoot(45, "运行时就绪，载入玄鉴引擎…");

    const resp = await fetch("engine.zip");
    if (!resp.ok) throw new Error("engine.zip 下载失败: " + resp.status);
    const buf = new Uint8Array(await resp.arrayBuffer());
    setBoot(65, "引擎包下载完成，解压中…");
    pyodide.FS.writeFile("/engine.zip", buf);

    pyodide.runPython(`
import zipfile, os, sys
os.makedirs("/engine", exist_ok=True)
with zipfile.ZipFile("/engine.zip") as z:
    z.extractall("/engine")
sys.path.insert(0, "/engine")
import engine_bridge
`);
    setBoot(95, "引擎初始化完成");
    const ready = pyodide.runPython("engine_bridge.ready()");
    console.log("engine ready:", ready, "type:", typeof ready);

    setBoot(100, "就绪");
    setTimeout(() => $("#boot").classList.add("hide"), 350);
  } catch (e) {
    const msg = (e && e.stack) ? e.stack : (e && e.message ? e.message : String(e));
    setBoot(100, "引擎加载失败：\n" + msg);
    console.error(e);
  }
}

/* ---------- 调用引擎 ---------- */
async function eng(fn, args) {
  const a = args.map((x) => JSON.stringify(x)).join(", ");
  const r = await pyodide.runPythonAsync(`engine_bridge.${fn}(${a})`);
  return JSON.parse(r);
}

/* ---------- 通用表单（八字/紫微共用） ---------- */
function buildCommon(id) {
  const opts = [];
  for (let h = 0; h <= 23; h++) {
    const label = h === 23 ? "23(晚子时)" : h;
    const sel = (h === 10) ? " selected" : "";
    opts.push(`<option value="${h}"${sel}>${label}</option>`);
  }
  $("#" + id).innerHTML = `
    <label>年<input type="number" id="${id}-y" value="1985" min="1900" max="2100"></label>
    <label>月<input type="number" id="${id}-m" value="4" min="1" max="12"></label>
    <label>日<input type="number" id="${id}-d" value="12" min="1" max="31"></label>
    <label>时辰<select id="${id}-h">${opts.join("")}</select></label>
    <label>性别<select id="${id}-g"><option>男</option><option>女</option></select></label>`;
}

/* ---------- 渲染 ---------- */
function esc(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function renderBazi(d) {
  const pillars = d.四柱.map((p) => `<span class="chip">${esc(p)}</span>`).join("");
  const steps = d.过程.map((s) => esc(s)).join("\n");
  const shi = (d.释读 || []).map((s) => `<div>· ${esc(s)}</div>`).join("");
  return `<div class="chips">${pillars}
      <span class="chip">天干 ${d.天干分}</span>
      <span class="chip">地支 ${d.地支分}</span>
      <span class="chip">总分 ${d.总分}</span>
      <span class="chip gold">档位 · ${esc(d.档位)}</span></div>
    <h3>判定过程</h3><div class="pre">${steps}</div>
    <h3>档位释义</h3>${shi}`;
}

function renderZiwei(d) {
  const meta = `<div class="chips">
    <span class="chip gold">命宫 ${esc(d.命宫.干支)}</span>
    <span class="chip">身宫 ${esc(d.身宫.干支)}</span>
    <span class="chip">命主 ${esc(d.命主)}</span>
    <span class="chip">身主 ${esc(d.身主)}</span>
    <span class="chip">五行局 ${esc(d.五行局)}</span>
    <span class="chip">${esc(d.大限顺逆)}</span>
    <span class="chip">起运虚岁 ${esc(d.起运虚岁)}</span></div>`;
  const grid = `<div class="palaces">` + d.十二宫.map((p) => {
    const stars = (p.主星 && p.主星.length) ? p.主星.join(" ") : "（空宫）";
    const cls = "palace" + (p.是命宫 ? " ming" : "");
    return `<div class="${cls}"><b>${esc(p.宫名)}</b> ${esc(p.干支)}<br>${esc(stars)}</div>`;
  }).join("") + `</div>`;
  return meta + grid + `<h3>完整盘</h3><div class="pre">${esc(d.text)}</div>`;
}

function renderText(t){return `<div class="pre">${esc(t)}</div>`;}

/* ---------- 处理器 ---------- */
async function runBazi() {
  const y=$("#form-bazi-common-y").value, m=$("#form-bazi-common-m").value,
        d=$("#form-bazi-common-d").value, h=$("#form-bazi-common-h").value;
  return renderBazi(await eng("bazi",[y,m,d,h]));
}
async function runZiwei() {
  const y=$("#form-ziwei-common-y").value, m=$("#form-ziwei-common-m").value,
        d=$("#form-ziwei-common-d").value, h=$("#form-ziwei-common-h").value,
        g=$("#form-ziwei-common-g").value;
  return renderZiwei(await eng("ziwei",[y,m,d,h,g]));
}
async function runHuangli() {
  const y=$("#hl-y").value,m=$("#hl-m").value,d=$("#hl-d").value,h=$("#hl-h").value;
  return renderText((await eng("huangli",[y,m,d,h])).text);
}
async function runLiuren() {
  const mode=$("#lr-mode .seg-btn.active").dataset.mode;
  let r;
  if(mode==="num"){
    r=await eng("xiaoliuren_number",[$("#lr-number").value,$("#lr-event").value]);
  }else{
    r=await eng("xiaoliuren_lunar",[$("#lr-m").value,$("#lr-d").value,$("#lr-sh").value,$("#lr-event").value]);
  }
  return renderText(r.text);
}
async function runQiming() {
  const r=await eng("qiming",[$("#qm-name").value,$("#qm-strokes").value,$("#qm-fl").value,$("#qm-tone").value]);
  return renderText(r.text);
}

const ACT={bazi:[runBazi,"#out-bazi"],ziwei:[runZiwei,"#out-ziwei"],huangli:[runHuangli,"#out-huangli"],liuren:[runLiuren,"#out-liuren"],qiming:[runQiming,"#out-qiming"]};

/* ---------- 交互 ---------- */
document.addEventListener("DOMContentLoaded",()=>{
  buildCommon("form-bazi-common");
  buildCommon("form-ziwei-common");

  $$(".tab").forEach(t=>t.addEventListener("click",()=>{
    $$(".tab").forEach(x=>x.classList.remove("active"));
    $$(".panel").forEach(x=>x.classList.remove("active"));
    t.classList.add("active");
    $("#tab-"+t.dataset.tab).classList.add("active");
  }));

  $$(".seg-btn").forEach(b=>b.addEventListener("click",()=>{
    $$("#lr-mode .seg-btn").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    const num=b.dataset.mode==="num";
    $("#lr-num").style.display=num?"flex":"none";
    $("#lr-lunar").style.display=num?"none":"flex";
  }));

  $$(".run").forEach(btn=>btn.addEventListener("click",async()=>{
    const [fn,out]=ACT[btn.dataset.act];
    const old=btn.textContent; btn.disabled=true; btn.textContent="计算中…";
    try{ $(out).innerHTML=await fn(); }
    catch(e){ $(out).innerHTML=`<span style="color:var(--red)">出错了：${esc(e.message||e)}</span>`; console.error(e); }
    finally{ btn.disabled=false; btn.textContent=old; }
  }));

  // 注册 Service Worker（离线缓存）
  if("serviceWorker" in navigator){
    navigator.serviceWorker.register("sw.js").catch(e=>console.warn("SW 注册失败(不影响使用)：",e));
  }

  boot().catch(e=>{
    const msg=(e&&e.message)?e.message:String(e);
    setBoot(100,"引擎加载失败："+msg);
    console.error(e);
  });
});
