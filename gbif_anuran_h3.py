"""
台灣無尾目 (Anura) GBIF — 分頁抓取 → H3 伺服器端聚合 → deck.gl H3HexagonLayer

示範用艾氏樹蛙 Kurixalus eiffingeri(台灣 ~11k 筆,< Search API 的 100k offset 上限,
故可匿名翻頁,免 GBIF 帳號)。重點:
  第 2 步  Search API 真實分頁(300/頁,迴圈 offset)
  第 5 步  幾千~上萬點不直接丟瀏覽器,而是先用 H3 聚合成數百個六角格 → H3HexagonLayer

資料量 >100k(如樹蛙科 189k、全 Anura 545k)時 Search API 翻不到,需改 Download API(要帳號、給 DOI)。

相依:  pip install pygbif pandas h3 pydeck matplotlib
執行:  python gbif_anuran_h3.py
"""

import json
import time

import pandas as pd
import h3
import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from pygbif import species, occurrences

# ----------------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------------
SPECIES_NAME = "Kurixalus eiffingeri"   # 艾氏樹蛙
COUNTRY = "TW"
H3_RES = 7                 # res7 ≈ 邊長 1.2km / 面積 5.2km²,適合全島熱區
TAIWAN_BBOX = (119.5, 21.5, 122.5, 25.5)   # lng_min, lat_min, lng_max, lat_max
BAD_ISSUES = {"ZERO_COORDINATE", "COORDINATE_OUT_OF_RANGE",
              "COORDINATE_INVALID", "COUNTRY_COORDINATE_MISMATCH"}
SEARCH_OFFSET_CAP = 100_000   # GBIF Search API 硬上限

HEX_GEOJSON_OUT = "anuran_h3.geojson"
MAP_OUT = "anuran_h3_map.html"
CMAP = "inferno"


# ----------------------------------------------------------------------------
# 第 1 步:學名 -> usageKey
# ----------------------------------------------------------------------------
def resolve_key(name):
    h = species.name_backbone(scientificName=name, taxonRank="SPECIES", strict=False)
    u = h.get("usage", h)
    return u.get("key") or h.get("usageKey")


# ----------------------------------------------------------------------------
# 第 2 步:Search API 分頁抓取
# ----------------------------------------------------------------------------
def fetch_all(taxon_key, page=300):
    total = occurrences.search(taxonKey=taxon_key, country=COUNTRY,
                               hasCoordinate=True, limit=0)["count"]
    print(f"  GBIF 回報總數: {total:,}")
    if total > SEARCH_OFFSET_CAP:
        print(f"  ⚠ 超過 {SEARCH_OFFSET_CAP:,} offset 上限,Search API 翻不完,需改 Download API")

    records, offset, t0 = [], 0, time.time()
    while offset < min(total, SEARCH_OFFSET_CAP):
        resp = occurrences.search(taxonKey=taxon_key, country=COUNTRY,
                                  hasCoordinate=True, hasGeospatialIssue=False,
                                  limit=page, offset=offset)
        batch = resp.get("results", [])
        if not batch:
            break
        records.extend(batch)
        offset += page
        if offset % 3000 == 0:
            print(f"    ...已抓 {len(records):,} 筆")
        if resp.get("endOfRecords"):
            break
    print(f"  分頁完成: {len(records):,} 筆,耗時 {time.time()-t0:.1f}s,共 {offset//page} 次請求")
    return records


# ----------------------------------------------------------------------------
# 第 3 步:輕量清洗(密度圖以保留最多有效點為主)
# ----------------------------------------------------------------------------
def clean(records):
    df = pd.DataFrame(records)
    n0 = len(df)
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude"])
    if "issues" in df:
        df = df[~df["issues"].apply(lambda x: bool(BAD_ISSUES & set(x or [])))]
    lng0, lat0, lng1, lat1 = TAIWAN_BBOX
    df = df[df["decimalLongitude"].between(lng0, lng1)
            & df["decimalLatitude"].between(lat0, lat1)]
    if "gbifID" in df:
        df = df.drop_duplicates(subset="gbifID")
    print(f"  清洗: {n0:,} -> {len(df):,}")
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------------
# 第 5 步a:H3 聚合(把上萬點壓成數百格)
# ----------------------------------------------------------------------------
def aggregate_h3(df, res):
    cells = [h3.latlng_to_cell(lat, lng, res)
             for lat, lng in zip(df["decimalLatitude"], df["decimalLongitude"])]
    agg = pd.Series(cells).value_counts().rename_axis("hex").reset_index(name="count")
    print(f"  H3 res{res}: {len(df):,} 點 -> {len(agg):,} 格 "
          f"(壓縮比 {len(df)/max(len(agg),1):.1f}×),最熱格 {agg['count'].max():,} 筆")

    # 依 log(count) 上色(分布右偏,線性會看不出差異)
    import math
    logv = agg["count"].map(lambda v: math.log1p(v))
    norm = mcolors.Normalize(vmin=logv.min(), vmax=logv.max())
    cmap = matplotlib.colormaps[CMAP]
    agg["color"] = logv.map(lambda v: [int(c * 255) for c in cmap(norm(v))[:3]] + [200])
    return agg


# ----------------------------------------------------------------------------
# 第 5 步b:輸出聚合 GeoJSON(可攜) + pydeck H3HexagonLayer 互動圖
# ----------------------------------------------------------------------------
def to_hex_geojson(agg, path):
    feats = []
    for _, r in agg.iterrows():
        boundary = h3.cell_to_boundary(r["hex"])      # [(lat,lng), ...]
        ring = [[lng, lat] for lat, lng in boundary]
        ring.append(ring[0])
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"hex": r["hex"], "count": int(r["count"])},
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f,
                  ensure_ascii=False)
    print(f"  聚合 GeoJSON -> {path} ({len(feats)} 格)")


def build_map(agg, path):
    import pydeck as pdk
    layer = pdk.Layer(
        "H3HexagonLayer",
        data=agg,
        get_hexagon="hex",
        get_fill_color="color",
        get_elevation="count",
        elevation_scale=30,
        extruded=True,
        pickable=True,
        opacity=0.85,
        coverage=0.95,
    )
    view = pdk.ViewState(latitude=23.7, longitude=120.9, zoom=7, pitch=45)
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={"text": "觀測數: {count}"},
        map_style="light",
    )
    deck.to_html(path)
    print(f"  互動地圖 -> {path}")


def main():
    print(f"目標: {SPECIES_NAME} @ {COUNTRY}")
    key = resolve_key(SPECIES_NAME)
    print(f"第 1 步: usageKey = {key}")

    print("第 2 步: Search API 分頁")
    records = fetch_all(key)

    print("第 3 步: 清洗")
    df = clean(records)

    print(f"第 5 步: H3 聚合 (res{H3_RES})")
    agg = aggregate_h3(df, H3_RES)

    to_hex_geojson(agg, HEX_GEOJSON_OUT)
    try:
        build_map(agg, MAP_OUT)
    except ImportError:
        print("  未裝 pydeck,略過地圖")


if __name__ == "__main__":
    main()
