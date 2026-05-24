"""
台灣特有山椒魚 (Hynobius) — 發文等級地形暈渲分布圖

讀 salamander.geojson(已清洗的 54 筆)→ 重投影到 Web Mercator
→ 疊在 Esri World Hillshade 暈渲底圖上 → 加製圖元素 → 輸出 300dpi PNG。

技術重點:
  - 暈渲底圖:contextily 抓 Esri.WorldHillshade 圖磚(免自下載 DEM / GDAL)
  - 投影:pyproj 4326 -> 3857,點位才能對齊圖磚
  - 比例尺:依中心緯度修正 Mercator 變形(cos φ),畫出「真實地面距離」
  - 製圖furniture:圖例(含各種筆數)、比例尺、指北針、資料來源

相依:  pip install matplotlib contextily pyproj
執行:  python salamander_hillshade.py
"""

import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrow
from pyproj import Transformer
import contextily as cx

GEOJSON_IN = "salamander.geojson"
PNG_OUT = "salamander_hillshade.png"

SPECIES_COLORS = {
    "Hynobius formosanus":  "#e41a1c",   # 台灣山椒魚
    "Hynobius sonani":      "#377eb8",   # 楚南氏
    "Hynobius arisanensis": "#4daf4a",   # 阿里山
    "Hynobius fucus":       "#984ea3",   # 觀霧
    "Hynobius glacialis":   "#ff7f00",   # 南湖
}
SPECIES_ZH = {
    "Hynobius formosanus":  "台灣山椒魚",
    "Hynobius sonani":      "楚南氏山椒魚",
    "Hynobius arisanensis": "阿里山山椒魚",
    "Hynobius fucus":       "觀霧山椒魚",
    "Hynobius glacialis":   "南湖山椒魚",
}


def setup_cjk_font():
    """matplotlib 預設字型沒有中文字,挑一個 macOS 上有的 CJK 字型。"""
    candidates = ["PingFang TC", "PingFang HK", "Heiti TC", "Arial Unicode MS",
                  "Hiragino Sans GB", "Songti SC", "STHeiti"]
    # 用已解析的字型清單,避免重讀到壞掉的字型檔
    available = {f.name for f in fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "sans-serif"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return None


def load_points(path):
    """讀 GeoJSON,回傳 (lon, lat, intended_name) 三串。"""
    gj = json.load(open(path, encoding="utf-8"))
    lons, lats, names = [], [], []
    for f in gj["features"]:
        x, y = f["geometry"]["coordinates"]
        lons.append(x)
        lats.append(y)
        names.append(f["properties"].get("_intended_name") or
                     f["properties"].get("species") or "其他")
    return lons, lats, names


def add_scalebar(ax, length_km=20):
    """在 Web Mercator 軸上畫『真實地面』比例尺。
    Mercator 在緯度 φ 會把距離放大 1/cos φ,所以 length_m 對應的軸寬要除以 cos φ。"""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    # 由軸中心的 Mercator y 反推緯度
    t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    _, lat_center = t.transform((x0 + x1) / 2, (y0 + y1) / 2)
    bar_axis_units = (length_km * 1000) / math.cos(math.radians(lat_center))

    pad = (x1 - x0) * 0.06
    bx = x0 + pad
    by = y0 + (y1 - y0) * 0.06
    ax.plot([bx, bx + bar_axis_units], [by, by], color="black", lw=3,
            solid_capstyle="butt", zorder=10)
    ax.text(bx + bar_axis_units / 2, by + (y1 - y0) * 0.012, f"{length_km} km",
            ha="center", va="bottom", fontsize=9, zorder=10)


def add_north_arrow(ax):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    nx = x1 - (x1 - x0) * 0.06
    ny = y0 + (y1 - y0) * 0.10
    ax.add_patch(FancyArrow(nx, ny, 0, (y1 - y0) * 0.05, width=0,
                            head_width=(x1 - x0) * 0.018,
                            head_length=(y1 - y0) * 0.022,
                            color="black", zorder=10))
    ax.text(nx, ny + (y1 - y0) * 0.075, "N", ha="center", va="bottom",
            fontweight="bold", fontsize=12, zorder=10)


def main():
    font = setup_cjk_font()
    print(f"CJK 字型: {font or '找不到,中文可能顯示為方框'}")

    lons, lats, names = load_points(GEOJSON_IN)
    print(f"讀入 {len(lons)} 點")

    # 4326 -> 3857
    to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    xs, ys = to_merc.transform(lons, lats)

    fig, ax = plt.subplots(figsize=(9, 11), dpi=300)

    # 依種分組畫點,順便統計筆數
    counts = {}
    for sp, color in SPECIES_COLORS.items():
        gx = [x for x, n in zip(xs, names) if n == sp]
        gy = [y for y, n in zip(ys, names) if n == sp]
        counts[sp] = len(gx)
        if gx:
            ax.scatter(gx, gy, s=70, c=color, edgecolors="white", linewidths=0.8,
                       zorder=5, alpha=0.95)

    # 視窗:資料範圍 + padding
    padx = (max(xs) - min(xs)) * 0.25 + 5000
    pady = (max(ys) - min(ys)) * 0.12 + 5000
    ax.set_xlim(min(xs) - padx, max(xs) + padx)
    ax.set_ylim(min(ys) - pady, max(ys) + pady)

    # 暈渲底圖
    cx.add_basemap(ax, source=cx.providers.Esri.WorldShadedRelief,
                   crs="EPSG:3857", attribution=False)

    ax.set_axis_off()
    add_scalebar(ax, length_km=20)
    add_north_arrow(ax)

    # 固定邊距,讓上方標題、下方出處有獨立空間(不用 tight 裁切以免座標位移)
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.03, right=0.97)

    # 標題 + 副標題
    fig.text(0.5, 0.955, "台灣特有山椒魚分布  Hynobius spp.",
             ha="center", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.925,
             "冰河孑遺的高山活化石 — 清洗後 n=54(已排除座標不確定性 >10 km 的模糊化記錄)",
             ha="center", fontsize=10.5, color="#444")

    # 圖例(含筆數)
    handles = [Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                      markerfacecolor=c, markeredgecolor="white",
                      label=f"{SPECIES_ZH[sp]}  {sp}  (n={counts[sp]})")
               for sp, c in SPECIES_COLORS.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5,
              framealpha=0.9, title="物種", title_fontsize=9)

    # 資料來源 / 製圖出處
    fig.text(0.5, 0.045,
             "資料:GBIF occurrence(search API)  |  底圖:Esri World Hillshade, USGS  |  "
             "投影:Web Mercator (EPSG:3857)\n"
             "※ 注意:多數記錄座標被模糊化至 ~30 km 網格以保護瀕危物種;正式發表建議改用 GBIF download API 取得 DOI",
             ha="center", fontsize=7.5, color="#666")

    fig.savefig(PNG_OUT, facecolor="white")
    print(f"輸出 -> {PNG_OUT}")
    for sp, n in counts.items():
        print(f"  {SPECIES_ZH[sp]:<7} {sp:<24} n={n}")


if __name__ == "__main__":
    main()
