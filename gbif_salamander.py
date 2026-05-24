"""
台灣特有種山椒魚 (Hynobius) GBIF occurrence 抓取 → 清洗 → GeoJSON / pydeck 視覺化

流程 (對應你提的 6 階段):
  1. 查物種 usageKey      name_backbone()
  2. 查 occurrence        occurrences.search() 分頁
  3. 座標品質清洗         issue flags + 台灣 bbox + uncertainty + 去重   ← 重點
  4. 轉地理格式           dict -> GeoJSON Feature
  5. 空間聚合 + 視覺化    pydeck HexagonLayer (密度) + ScatterplotLayer (點)  ← 重點
  6. 輸出                 salamander.geojson + salamander_map.html

相依套件:  pip install pygbif pandas pydeck
執行:      python gbif_salamander.py
"""

import json
from collections import Counter

import pandas as pd
from pygbif import species, occurrences

# ----------------------------------------------------------------------------
# 設定區
# ----------------------------------------------------------------------------
SPECIES = [
    "Hynobius formosanus",    # 台灣山椒魚
    "Hynobius sonani",        # 楚南氏山椒魚
    "Hynobius arisanensis",   # 阿里山山椒魚
    "Hynobius fucus",         # 觀霧山椒魚 (一併納入,屬內台灣特有)
    "Hynobius glacialis",     # 南湖山椒魚
]
COUNTRY = "TW"

# --- 第 3 步的清洗門檻 ---
# 台灣本島 bounding box (lng_min, lat_min, lng_max, lat_max);超出此框 = 可疑
TAIWAN_BBOX = (119.5, 21.5, 122.5, 25.5)
# 座標不確定性上限 (公尺);None 值(未填)預設保留,但會標記
MAX_UNCERTAINTY_M = 10_000
# 視為「壞點」直接剔除的 GBIF issue flags
BAD_ISSUES = {
    "ZERO_COORDINATE",
    "COORDINATE_OUT_OF_RANGE",
    "COORDINATE_INVALID",
    "COUNTRY_COORDINATE_MISMATCH",
    "PRESUMED_SWAPPED_COORDINATE",
    "PRESUMED_NEGATED_LONGITUDE",
    "PRESUMED_NEGATED_LATITUDE",
}

GEOJSON_OUT = "salamander.geojson"
MAP_OUT = "salamander_map.html"

# 每種給一個顏色 (RGB),供 pydeck 點圖用
SPECIES_COLORS = {
    "Hynobius formosanus":  [228, 26, 28],
    "Hynobius sonani":      [55, 126, 184],
    "Hynobius arisanensis": [77, 175, 74],
    "Hynobius fucus":       [152, 78, 163],
    "Hynobius glacialis":   [255, 127, 0],
}
DEFAULT_COLOR = [120, 120, 120]


# ----------------------------------------------------------------------------
# 第 1 步:學名 -> usageKey
# ----------------------------------------------------------------------------
def resolve_keys(names):
    """用 GBIF backbone 把學名解析成 usageKey,避免同物異名漏抓。"""
    resolved = {}
    for name in names:
        # pygbif >=0.6: 參數是 scientificName / taxonRank (舊版為 name / rank)
        hit = species.name_backbone(scientificName=name, taxonRank="SPECIES", strict=False)
        # 新版回傳巢狀 {"usage": {"key", "name", "status"}};舊版為扁平 usageKey
        usage = hit.get("usage", hit)
        key = usage.get("key") or hit.get("usageKey")
        status = usage.get("status") or hit.get("status", "?")
        matched = usage.get("name") or hit.get("scientificName", "—")
        if key:
            resolved[name] = key
            print(f"  ✓ {name:<24} key={key}  [{status}] -> {matched}")
        else:
            print(f"  ✗ {name:<24} 找不到 backbone match,略過")
    return resolved


# ----------------------------------------------------------------------------
# 第 2 步:抓 occurrence (分頁)
# ----------------------------------------------------------------------------
def fetch_occurrences(intended_name, taxon_key, page=300, hard_cap=10_000):
    """search API 單次上限 300,迴圈翻頁直到 endOfRecords。
    資料量大時應改用 GBIF download API(會給 DOI),此處族群小,search 足矣。"""
    records, offset = [], 0
    while offset < hard_cap:
        resp = occurrences.search(
            taxonKey=taxon_key,
            country=COUNTRY,
            hasCoordinate=True,          # 先在 server 端濾掉無座標
            hasGeospatialIssue=False,    # server 端先擋掉明顯地理問題
            limit=page,
            offset=offset,
        )
        batch = resp.get("results", [])
        for r in batch:
            r["_intended_name"] = intended_name   # 記住我們「想找」的種名
        records.extend(batch)
        if resp.get("endOfRecords") or not batch:
            break
        offset += page
    return records


# ----------------------------------------------------------------------------
# 第 3 步:座標品質清洗 (重點)
# ----------------------------------------------------------------------------
def clean(records):
    """逐層過濾並印出每層留下的筆數,讓品質決策透明可追。"""
    df = pd.DataFrame(records)
    report = {"0_raw": len(df)}
    if df.empty:
        return df, report

    # (a) 必須有經緯度
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude"])
    report["1_has_latlng"] = len(df)

    # (b) 只留 PRESENT (排除 ABSENT 的不存在記錄)
    if "occurrenceStatus" in df:
        df = df[df["occurrenceStatus"].fillna("PRESENT") == "PRESENT"]
    report["2_present"] = len(df)

    # (c) 剔除帶壞 issue flag 的記錄
    def has_bad_issue(issues):
        return bool(BAD_ISSUES & set(issues or []))
    if "issues" in df:
        df = df[~df["issues"].apply(has_bad_issue)]
    report["3_issue_ok"] = len(df)

    # (d) 台灣 bbox 內 —— 抓「大西洋上的山椒魚」這種經典錯誤
    lng_min, lat_min, lng_max, lat_max = TAIWAN_BBOX
    df = df[
        df["decimalLongitude"].between(lng_min, lng_max)
        & df["decimalLatitude"].between(lat_min, lat_max)
    ]
    report["4_in_taiwan_bbox"] = len(df)

    # (e) 座標不確定性門檻 (未填者保留,但標記)
    if "coordinateUncertaintyInMeters" in df:
        unc = pd.to_numeric(df["coordinateUncertaintyInMeters"], errors="coerce")
        df = df[unc.isna() | (unc <= MAX_UNCERTAINTY_M)]
    report["5_uncertainty_ok"] = len(df)

    # (f) 去重:同一筆 gbifID 不重複
    if "gbifID" in df:
        df = df.drop_duplicates(subset="gbifID")
    report["6_dedup"] = len(df)

    return df.reset_index(drop=True), report


# ----------------------------------------------------------------------------
# 第 4 步:轉 GeoJSON
# ----------------------------------------------------------------------------
def to_geojson(df):
    keep = [
        "gbifID", "_intended_name", "species", "scientificName",
        "year", "eventDate", "datasetName", "basisOfRecord",
        "coordinateUncertaintyInMeters",
    ]
    feats = []
    for _, row in df.iterrows():
        props = {k: row.get(k) for k in keep if k in df.columns}
        # 把 NaN 轉成 None 讓 JSON 合法
        props = {k: (None if pd.isna(v) else v) for k, v in props.items()}
        feats.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row["decimalLongitude"], row["decimalLatitude"]],
            },
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": feats}


# ----------------------------------------------------------------------------
# 第 5 步:pydeck 視覺化 (HexagonLayer 密度 + 點圖)
# ----------------------------------------------------------------------------
def build_map(df):
    import pydeck as pdk

    df = df.copy()
    df["lon"] = df["decimalLongitude"]
    df["lat"] = df["decimalLatitude"]
    name_col = df["_intended_name"].fillna(df.get("species", ""))
    df["color"] = name_col.map(SPECIES_COLORS).apply(
        lambda c: c if isinstance(c, list) else DEFAULT_COLOR
    )
    df["label"] = name_col

    hexagon = pdk.Layer(
        "HexagonLayer",
        data=df,
        get_position="[lon, lat]",
        radius=1000,            # 1km 六角格;山椒魚分布窄,格子要小
        elevation_scale=20,
        extruded=True,
        pickable=True,
        coverage=0.9,
    )
    points = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=300,
        pickable=True,
        opacity=0.8,
    )
    view = pdk.ViewState(latitude=23.9, longitude=121.0, zoom=7, pitch=40)
    deck = pdk.Deck(
        layers=[hexagon, points],
        initial_view_state=view,
        tooltip={"text": "{label}\n{datasetName}"},
        map_style="road",
    )
    deck.to_html(MAP_OUT)
    print(f"  互動地圖 -> {MAP_OUT}")


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def main():
    print("第 1 步:解析學名 -> usageKey")
    keys = resolve_keys(SPECIES)

    print("\n第 2 步:抓取 occurrence")
    all_records = []
    for name, key in keys.items():
        recs = fetch_occurrences(name, key)
        print(f"  {name:<24} 抓到 {len(recs)} 筆 (清洗前)")
        all_records.extend(recs)

    print("\n第 3 步:座標品質清洗")
    df, report = clean(all_records)
    for stage, n in report.items():
        print(f"  {stage:<20} {n}")

    if df.empty:
        print("\n清洗後無資料,結束。")
        return

    print("\n  清洗後各種筆數:")
    for name, n in Counter(df["_intended_name"]).most_common():
        print(f"    {name:<24} {n}")

    print("\n第 4 步:輸出 GeoJSON")
    gj = to_geojson(df)
    with open(GEOJSON_OUT, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)
    print(f"  {len(gj['features'])} features -> {GEOJSON_OUT}")

    print("\n第 5 步:建互動地圖")
    try:
        build_map(df)
    except ImportError:
        print("  未安裝 pydeck,略過地圖 (pip install pydeck)")


if __name__ == "__main__":
    main()
