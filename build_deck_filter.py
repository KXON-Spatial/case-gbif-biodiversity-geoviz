"""
讀 anuran_multi_h3.json → 產生含「物種下拉 + 年代滑桿」的 deck.gl + MapLibre 互動地圖。

設計:
  - 六角格邊界在 Python 端用 h3 先算好並 inline(前端不需 h3-js,避免 UMD bundle 沒打包 h3 的雷)
  - 用 deck.gl 內建 PolygonLayer 畫六角格(一定在 bundle 裡)
  - overlaid 模式:deck 畫在底圖上層,不會被底圖填色蓋住
  - 篩選(物種/年份)在前端 groupby-sum,即時重建圖層

執行:  python build_deck_filter.py
"""
import json
from datetime import date
import h3

JSON_IN = "anuran_multi_h3.json"
HTML_OUT = "anuran_filter_map.html"
CENTER = [120.9, 23.7]
ZOOM = 7.0
ELEV_SCALE = 35
GBIF_DOI = ""   # 跑 Download API 取得後填入,例:"10.15468/dl.xxxxxx"


def main():
    payload = json.load(open(JSON_IN, encoding="utf-8"))

    # 預算每個 hex 的多邊形邊界([lng,lat] 閉合環),inline 給前端
    hexes = {}
    for d in payload["data"]:
        h_ = d["h"]
        if h_ not in hexes:
            ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(h_)]
            ring.append(ring[0])
            hexes[h_] = ring
    print(f"物種 {len(payload['species'])} 種,{len(payload['data']):,} 列,"
          f"{len(hexes):,} 個唯一六角格,年份 {payload['yearMin']}–{payload['yearMax']}")

    html = TEMPLATE
    for k, v in {
        "__PAYLOAD__": json.dumps(payload, ensure_ascii=False),
        "__HEXES__": json.dumps(hexes),
        "__CENTER__": json.dumps(CENTER),
        "__ZOOM__": str(ZOOM),
        "__ELEV__": str(ELEV_SCALE),
        "__FETCHED__": payload.get("fetched") or date.today().isoformat(),
        "__DOI__": f" · DOI: {GBIF_DOI}" if GBIF_DOI else "",
    }.items():
        html = html.replace(k, v)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"輸出 -> {HTML_OUT}")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>台灣樹蛙分布 · 互動篩選</title>
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/nouislider@15/dist/nouislider.min.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/deck.gl@9/dist.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/nouislider@15/dist/nouislider.min.js"></script>
<style>
  html,body{margin:0;height:100%;background:#0b0b10;
    font-family:"PingFang TC",system-ui,sans-serif;}
  #map{position:absolute;inset:0;}
  .panel{position:absolute;z-index:2;color:#f2f2f2;text-shadow:0 1px 4px rgba(0,0,0,.8);}
  #title{top:16px;left:20px;background:rgba(13,16,22,.74);padding:12px 16px;
    border-radius:10px;backdrop-filter:blur(2px);}
  #title h1{margin:0;font-size:21px;font-weight:700;}
  #title p{margin:4px 0 0;font-size:12px;color:#cfcfcf;}
  #controls{top:16px;right:16px;background:rgba(15,15,22,.82);padding:14px 16px;
    border-radius:10px;width:268px;text-shadow:none;}
  #controls label{font-size:12px;color:#cfcfcf;display:block;margin:0 0 5px;}
  #controls select{width:100%;padding:6px 8px;border-radius:6px;border:1px solid #333;
    background:#1c1c26;color:#f2f2f2;font-size:13px;margin-bottom:16px;}
  #yr{margin:10px 6px 6px;}
  #yrlabel{font-size:13px;color:#fff;font-weight:600;}
  #stat{margin-top:14px;font-size:11.5px;color:#9fd;line-height:1.5;}
  .noUi-connect{background:#3aaf5e;}
  .noUi-handle{box-shadow:none;}
  #legend{bottom:26px;left:20px;background:rgba(15,15,22,.72);padding:11px 13px;
    border-radius:8px;font-size:12px;}
  #legend .bar{height:11px;width:190px;border-radius:3px;margin:6px 0 4px;
    background:linear-gradient(to right,rgb(12,70,40),rgb(0,104,55),
      rgb(35,160,75),rgb(120,200,100),rgb(200,255,120));}
  #legend .ticks{display:flex;justify-content:space-between;color:#cfcfcf;}
  #legend .cite{margin-top:9px;font-size:9.5px;color:#8aa894;line-height:1.5;max-width:225px;}
  #attrib{bottom:6px;right:8px;font-size:10px;color:#aaa;}
</style>
</head>
<body>
<div id="map"></div>
<div id="title" class="panel">
  <h1>台灣樹蛙分布 · 互動篩選</h1>
  <p>GBIF occurrence · 資料更新 __FETCHED__ · H3 聚合 · deck.gl + MapLibre</p>
</div>
<div id="controls" class="panel">
  <label>物種</label>
  <select id="species"></select>
  <label>觀測年代</label>
  <div id="yr"></div>
  <div id="yrlabel"></div>
  <div id="stat"></div>
</div>
<div id="legend" class="panel">
  <div>觀測密度（每 H3 格,對數色階）</div>
  <div class="bar"></div>
  <div class="ticks"><span>少</span><span id="legmax">多</span></div>
  <div class="cite">資料 GBIF.org · 存取 __FETCHED__ · 含 CC BY-NC 4.0 授權,僅供非商業使用__DOI__</div>
</div>
<div id="attrib" class="panel">資料來源 GBIF · 底圖 © CARTO © OpenStreetMap</div>

<script>
const P = __PAYLOAD__;
const HEXES = __HEXES__;
const DATA = P.data, SPECIES = P.species;
const RAMP=[[12,70,40],[0,104,55],[35,160,75],[120,200,100],[200,255,120]];
let curMaxLog = 1;
function colorFor(c){
  const t=Math.min(1,Math.log1p(c)/curMaxLog);
  const x=t*(RAMP.length-1),i=Math.floor(x),f=x-i;
  const a=RAMP[i],b=RAMP[Math.min(i+1,RAMP.length-1)];
  return [a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f,235];
}

const sel=document.getElementById("species");
sel.add(new Option("全部物種","ALL"));
SPECIES.forEach((s,i)=>sel.add(new Option(`${s.zh}  ${s.name}`,String(i))));

const map=new maplibregl.Map({
  container:"map",
  style:"https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  center:__CENTER__, zoom:__ZOOM__, pitch:48, bearing:-12, antialias:true
});
const lighting=new deck.LightingEffect({
  ambient:new deck.AmbientLight({color:[255,255,255],intensity:1.1}),
  sun:new deck.DirectionalLight({color:[255,255,255],intensity:1.4,direction:[-1,-3,-1]})
});
// overlaid 模式(interleaved:false):deck 畫在底圖上層,不會被底圖蓋住
const overlay=new deck.MapboxOverlay({interleaved:false,effects:[lighting],layers:[],
  getTooltip:({object})=>object&&{
    html:`觀測數 <b>${object.count}</b>`,
    style:{background:"rgba(15,15,22,.9)",color:"#fff",padding:"6px 9px",borderRadius:"6px"}}
});
map.addControl(overlay);
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),"bottom-right");

const yr=document.getElementById("yr");
noUiSlider.create(yr,{start:[P.yearMin,P.yearMax],connect:true,step:1,
  range:{min:P.yearMin,max:P.yearMax},
  format:{to:v=>Math.round(v),from:v=>+v}});
let yearRange=[P.yearMin,P.yearMax];

function update(){
  const sp=sel.value, [y0,y1]=yearRange;
  const acc=new Map(); let total=0;
  for(const r of DATA){
    if(sp!=="ALL"&&r.s!==+sp) continue;
    if(r.y<y0||r.y>y1) continue;
    acc.set(r.h,(acc.get(r.h)||0)+r.c); total+=r.c;
  }
  const arr=[...acc].map(([h,c])=>({polygon:HEXES[h],count:c}));
  const maxc=arr.reduce((m,d)=>Math.max(m,d.count),1);
  curMaxLog=Math.log1p(maxc);
  overlay.setProps({layers:[new deck.PolygonLayer({
    id:"h3",data:arr,pickable:true,extruded:true,filled:true,wireframe:false,
    getPolygon:d=>d.polygon,getFillColor:d=>colorFor(d.count),
    getElevation:d=>d.count,elevationScale:__ELEV__,opacity:0.9,
    material:{ambient:0.5,diffuse:0.6,shininess:32,specularColor:[60,60,60]},
    updateTriggers:{getFillColor:[maxc],getElevation:[sp,y0,y1]}
  })]});
  document.getElementById("yrlabel").textContent=`${y0} – ${y1}`;
  document.getElementById("legmax").textContent=`多（最高 ${maxc}）`;
  const name=sp==="ALL"?"全部物種":SPECIES[+sp].zh;
  document.getElementById("stat").innerHTML=
    `${name}<br>觀測 <b>${total.toLocaleString()}</b> 筆 · 佔 <b>${arr.length}</b> 格`;
}

yr.noUiSlider.on("update",vals=>{yearRange=vals.map(Number);update();});
sel.addEventListener("change",update);
update();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
