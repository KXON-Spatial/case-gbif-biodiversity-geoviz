"""
把 H3 聚合 GeoJSON 包成「發文等級」的 deck.gl + MapLibre 獨立互動地圖。

- 底圖:CARTO dark-matter 向量圖磚(免費、免 token)
- 圖層:deck.gl H3HexagonLayer(3D 擠出 + YlOrRd 熱度色階 + 光照)
- 資料 inline 進 HTML,雙擊即開,不需本機伺服器
- 想換成真 Mapbox:把 STYLE_URL 換成 mapbox://... 並在 maplibre 改用 mapbox-gl + token(見 HTML 註解)

執行:  python build_deck_maplibre.py
"""

import json
from datetime import date

GEOJSON_IN = "anuran_h3.geojson"
HTML_OUT = "anuran_deck_map.html"
TITLE = "艾氏樹蛙 觀測密度熱區"
SUBTITLE = "Kurixalus eiffingeri · GBIF n=11,158 · H3 res7 聚合 (792 格)"
CENTER = [120.9, 23.7]   # lng, lat
ZOOM = 7.2
ELEV_SCALE = 22

# OG / canonical(此頁目前未進 CI 部署流程,留作將來獨立發布用)
SITE_URL = "https://spatial.kxon.net"
PAGE_PATH = "/eiffingeri.html"
OG_IMAGE = f"{SITE_URL}/salamander.png"
OG_DESC = "艾氏樹蛙 GBIF 11,158 筆觀測,H3 res7 聚合成 792 格,deck.gl 3D 擠出 + MapLibre 暗色底圖。"


def main():
    gj = json.load(open(GEOJSON_IN, encoding="utf-8"))
    data = [{"polygon": f["geometry"]["coordinates"][0],
             "count": f["properties"]["count"]}
            for f in gj["features"]]
    max_count = max(d["count"] for d in data)
    print(f"讀入 {len(data)} 格,最熱 {max_count} 筆")

    html = TEMPLATE
    for k, v in {
        "__DATA__": json.dumps(data, ensure_ascii=False),
        "__TITLE__": TITLE,
        "__SUBTITLE__": SUBTITLE,
        "__CENTER__": json.dumps(CENTER),
        "__ZOOM__": str(ZOOM),
        "__ELEV__": str(ELEV_SCALE),
        "__MAXCOUNT__": str(max_count),
        "__FETCHED__": date.today().isoformat(),
        "__PAGE_URL__": f"{SITE_URL}{PAGE_PATH}",
        "__OG_IMAGE__": OG_IMAGE,
        "__OG_DESC__": OG_DESC,
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
<title>__TITLE__ | KXON Spatial</title>
<meta name="description" content="__OG_DESC__" />
<link rel="canonical" href="__PAGE_URL__" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="KXON Spatial" />
<meta property="og:locale" content="zh_TW" />
<meta property="og:title" content="__TITLE__" />
<meta property="og:description" content="__OG_DESC__" />
<meta property="og:url" content="__PAGE_URL__" />
<meta property="og:image" content="__OG_IMAGE__" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="__TITLE__" />
<meta name="twitter:description" content="__OG_DESC__" />
<meta name="twitter:image" content="__OG_IMAGE__" />
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/deck.gl@9/dist.min.js"></script>
<style>
  html, body { margin: 0; height: 100%; background: #0b0b10;
    font-family: "PingFang TC", system-ui, sans-serif; }
  #map { position: absolute; inset: 0; }
  .panel { position: absolute; z-index: 2; color: #f2f2f2;
    text-shadow: 0 1px 4px rgba(0,0,0,.8); }
  #title { top: 18px; left: 20px; background: rgba(13,16,22,.74); padding: 12px 16px;
    border-radius: 10px; backdrop-filter: blur(2px); }
  #title h1 { margin: 0; font-size: 22px; font-weight: 700; }
  #title p  { margin: 4px 0 0; font-size: 12.5px; color: #cfcfcf; }
  #legend { bottom: 28px; left: 20px; background: rgba(15,15,22,.72);
    padding: 12px 14px; border-radius: 8px; font-size: 12px; }
  #legend .bar { height: 12px; width: 200px; border-radius: 3px; margin: 6px 0 4px;
    background: linear-gradient(to right,
      rgb(12,70,40), rgb(0,104,55), rgb(35,160,75),
      rgb(120,200,100), rgb(200,255,120)); }
  #legend .ticks { display: flex; justify-content: space-between; color: #cfcfcf; }
  #legend .cite { margin-top: 9px; font-size: 9.5px; color: #8aa894; line-height: 1.5;
    max-width: 235px; }
  #attrib { bottom: 6px; right: 8px; font-size: 10px; color: #aaa; }
  .tip { font-size: 13px; }
</style>
</head>
<body>
<div id="map"></div>
<div id="title" class="panel">
  <h1>__TITLE__</h1>
  <p>__SUBTITLE__ · 資料更新 __FETCHED__</p>
</div>
<div id="legend" class="panel">
  <div>觀測密度（每 H3 格,對數色階）</div>
  <div class="bar"></div>
  <div class="ticks"><span>少</span><span>多（最高 __MAXCOUNT__）</span></div>
  <div class="cite">資料 GBIF.org · 存取 __FETCHED__ · 含 CC BY-NC 4.0 授權,僅供非商業使用</div>
</div>
<div id="attrib" class="panel">資料來源 GBIF · 底圖 © CARTO © OpenStreetMap · deck.gl + MapLibre</div>

<script>
const DATA = __DATA__;
const MAXLOG = Math.log1p(__MAXCOUNT__);

// YlOrRd 色階(對數)。錨點與 CSS legend 一致。
const RAMP = [
  [12,70,40],[0,104,55],[35,160,75],[120,200,100],[200,255,120]
];
function colorFor(count) {
  const t = Math.min(1, Math.log1p(count) / MAXLOG);
  const x = t * (RAMP.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = RAMP[i], b = RAMP[Math.min(i + 1, RAMP.length - 1)];
  return [a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f, a[2]+(b[2]-a[2])*f, 235];
}

const map = new maplibregl.Map({
  container: "map",
  // 想換真 Mapbox:把這行改成 "mapbox://styles/mapbox/dark-v11",
  // 並改用 mapbox-gl.js + new mapboxgl.Map({accessToken: "你的 token", ...})
  style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  center: __CENTER__,
  zoom: __ZOOM__,
  pitch: 48,
  bearing: -12,
  antialias: true
});

const lighting = new deck.LightingEffect({
  ambient: new deck.AmbientLight({ color: [255,255,255], intensity: 1.1 }),
  sun: new deck.DirectionalLight({ color: [255,255,255], intensity: 1.4,
    direction: [-1, -3, -1] })
});

// 用內建 PolygonLayer 畫預算好的六角格邊界(避免 UMD bundle 未打包 h3-js 的雷)
const h3Layer = new deck.PolygonLayer({
  id: "anuran-h3",
  data: DATA,
  pickable: true,
  extruded: true,
  filled: true,
  wireframe: false,
  getPolygon: d => d.polygon,
  getFillColor: d => colorFor(d.count),
  getElevation: d => d.count,
  elevationScale: __ELEV__,
  opacity: 0.9,
  material: { ambient: 0.5, diffuse: 0.6, shininess: 32, specularColor: [60,60,60] }
});

const overlay = new deck.MapboxOverlay({
  interleaved: false,   // overlaid:deck 畫在底圖上層,不會被蓋住
  effects: [lighting],
  layers: [h3Layer],
  getTooltip: ({ object }) =>
    object && { html: `<div class="tip">觀測數 <b>${object.count}</b></div>`,
                style: { background: "rgba(15,15,22,.9)", color: "#fff",
                         padding: "6px 9px", borderRadius: "6px" } }
});

map.addControl(overlay);
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
