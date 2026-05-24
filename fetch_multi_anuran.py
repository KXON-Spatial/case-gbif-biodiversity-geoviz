"""
多物種 + 年份:抓 4 種台灣樹蛙 → 清洗 → 聚合成 (hex, 物種, 年份) → 計數。
輸出 anuran_multi_h3.json,供前端做物種下拉 + 年代滑桿的即時 groupby。

執行:  python fetch_multi_anuran.py
"""
import json
import time
from datetime import date

import pandas as pd
import h3
from pygbif import species, occurrences

SPECIES = [   # (學名, 中文)
    ("Zhangixalus moltrechti", "莫氏樹蛙"),
    ("Kurixalus eiffingeri",   "艾氏樹蛙"),
    ("Zhangixalus prasinatus", "翡翠樹蛙"),
    ("Zhangixalus arvalis",    "諸羅樹蛙"),
]
COUNTRY = "TW"
H3_RES = 7
TAIWAN_BBOX = (119.5, 21.5, 122.5, 25.5)
BAD_ISSUES = {"ZERO_COORDINATE", "COORDINATE_OUT_OF_RANGE",
              "COORDINATE_INVALID", "COUNTRY_COORDINATE_MISMATCH"}
YEAR_MIN_VALID, YEAR_MAX_VALID = 1950, 2026
OUT = "anuran_multi_h3.json"


def resolve_key(name):
    h = species.name_backbone(scientificName=name, strict=False)
    u = h.get("usage", h)
    return u.get("key") or h.get("usageKey")


def fetch_all(taxon_key, page=300):
    records, offset = [], 0
    while offset < 100_000:
        resp = occurrences.search(taxonKey=taxon_key, country=COUNTRY,
                                  hasCoordinate=True, hasGeospatialIssue=False,
                                  limit=page, offset=offset)
        batch = resp.get("results", [])
        if not batch:
            break
        records.extend(batch)
        offset += page
        if resp.get("endOfRecords"):
            break
    return records


def clean(df):
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude", "year"])
    if "issues" in df:
        df = df[~df["issues"].apply(lambda x: bool(BAD_ISSUES & set(x or [])))]
    lng0, lat0, lng1, lat1 = TAIWAN_BBOX
    df = df[df["decimalLongitude"].between(lng0, lng1)
            & df["decimalLatitude"].between(lat0, lat1)]
    df = df[df["year"].between(YEAR_MIN_VALID, YEAR_MAX_VALID)]
    if "gbifID" in df:
        df = df.drop_duplicates(subset="gbifID")
    return df


def main():
    t0 = time.time()
    species_meta, agg = [], {}   # agg[(hex, sidx, year)] = count
    for sidx, (sci, zh) in enumerate(SPECIES):
        key = resolve_key(sci)
        recs = fetch_all(key)
        df = pd.DataFrame(recs)
        df = clean(df)
        n = 0
        for lat, lng, yr in zip(df["decimalLatitude"], df["decimalLongitude"], df["year"]):
            cell = h3.latlng_to_cell(lat, lng, H3_RES)
            k = (cell, sidx, int(yr))
            agg[k] = agg.get(k, 0) + 1
            n += 1
        species_meta.append({"name": sci, "zh": zh, "n": int(n)})
        print(f"  [{sidx}] {zh} {sci}: 清洗後 {n:,} 筆,耗時累計 {time.time()-t0:.0f}s",
              flush=True)

    data = [{"h": h_, "s": s_, "y": y_, "c": c_} for (h_, s_, y_), c_ in agg.items()]
    years = [d["y"] for d in data]
    out = {
        "fetched": date.today().isoformat(),   # 抓取日期,給前端標示資料新鮮度
        "species": species_meta,
        "yearMin": min(years), "yearMax": max(years),
        "res": H3_RES,
        "data": data,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"輸出 -> {OUT}  ({len(data):,} 筆 (hex,物種,年) 列, "
          f"年份 {out['yearMin']}–{out['yearMax']})", flush=True)


if __name__ == "__main__":
    main()
