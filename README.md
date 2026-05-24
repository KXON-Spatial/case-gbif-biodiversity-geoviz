# 台灣生物多樣性 GBIF → 地理視覺化 Pipeline

把公開的生物觀測資料(GBIF)轉成「發文等級」的地理視覺化:從資料抓取、座標品質清洗、
空間聚合,到靜態地形暈渲圖與 deck.gl 互動地圖。以**台灣特有山椒魚**與**台灣樹蛙科**為案例。

---

## 1. 三大平台分工

這三個網站處在生態資料流的不同位置,理解分工最重要:

| 平台 | 定位 | 對本專案的角色 |
|---|---|---|
| **iNaturalist** | 公民科學觀測上傳(全類群、含照片) | 資料源頭;Research Grade 觀測會自動匯入 GBIF |
| **eBird** | 鳥類結構化清單(含 effort) | *時間維度*的豐度動畫之王(Status & Trends 模型柵格,經 R `ebirdst`);屬 raster pipeline |
| **GBIF** | 全球聚合層(~30 億筆) | 本專案的**資料後端**:`pygbif` 抓取、Maps API、DwC-A 下載(含 DOI) |

**選型結論**:要做「空間密度熱區(deck.gl HexagonLayer/H3)」→ 用 GBIF 點位資料(本專案);
要做「遷徙/季節的時間動畫」→ 才用 eBird 的柵格產品。兩者互補,不衝突。

---

## 2. 整體資料流(6 步)

```
1. 學名 → usageKey      name_backbone()(避免同物異名漏抓)
2. 抓 occurrence        Search API 分頁 / 或 Download API(視資料量)
3. 座標品質清洗 ★        issue flags + 台灣 bbox + uncertainty + 去重
4. 轉地理格式            GeoJSON / DataFrame
5. 空間聚合 + 視覺化 ★   H3 聚合 → 靜態暈渲圖 / deck.gl 互動地圖
6. 輸出                  PNG / GeoJSON / 互動 HTML
```

★ = 本專案最關鍵、最能展現工程價值的兩步。

---

## 3. 案例一:台灣特有山椒魚(嚴格清洗 + 地形暈渲)

**為什麼選**:冰河孑遺的高山活化石,分布極窄(中央山脈高海拔),是測試**座標品質清洗**的完美對象——任何落到平地/海上的點幾乎可確定是錯的。

**腳本**
- `gbif_salamander.py` — 抓 5 種 *Hynobius*、跑 6 步清洗漏斗、輸出 `salamander.geojson` + pydeck 地圖
- `salamander_hillshade.py` — 讀 GeoJSON → pyproj 重投影 → contextily 暈渲底圖 → 製圖元素 → `salamander_hillshade.png`(300 dpi)

**清洗漏斗結果**(293 → 54):

| 階段 | 筆數 |
|---|---|
| 原始 | 293 |
| 有經緯度 / PRESENT / issue OK | 293 |
| 台灣 bbox 內 | 293 |
| **不確定性 ≤ 10km** | **54** ← 砍掉 239 筆 |
| 去重 | 54 |

---

## 4. 案例二:台灣樹蛙科(海量分頁/Download API + H3 聚合 + 互動篩選)

**為什麼選**:台灣兩棲類公民科學極成熟,無尾目 GBIF 紀錄達數十萬筆,是測試**分頁/Download API 效能**與 **H3 空間聚合**的壓力測試。

**腳本**
- `gbif_anuran_h3.py` — 單種(艾氏樹蛙)示範:Search API 分頁 → H3 聚合 → pydeck H3 地圖
- `fetch_multi_anuran.py` — 4 種樹蛙、抓取+清洗+聚合成 `(hex, 物種, 年)` → `anuran_multi_h3.json`
- `build_deck_filter.py` — 產出含**物種下拉 + 年代滑桿**的 deck.gl + MapLibre 互動地圖 `anuran_filter_map.html`
- `build_deck_maplibre.py` — 產出單種版 deck.gl + MapLibre 暗色 3D 地圖

**示範資料**(4 種樹蛙,清洗後):

| 物種 | 清洗後筆數 | 分布特性 |
|---|---|---|
| 莫氏樹蛙 *Zhangixalus moltrechti* | 11,977 | 全島中海拔廣布 |
| 艾氏樹蛙 *Kurixalus eiffingeri* | 8,019 | 北部/東部竹林 |
| 翡翠樹蛙 *Z. prasinatus* | 6,753 | **僅北部** |
| 諸羅樹蛙 *Z. arvalis* | 2,261 | **僅西南低地(嘉南)** |

→ 聚合成 5,991 列 `(hex,物種,年)`,年份 1958–2026。

**互動設計的核心決策**:**聚合在後端做一次**,**篩選在前端做**(純 groupby-sum)。
拖滑桿/切下拉完全不重打 GBIF,所以是瞬間反應、也不對 GBIF 失禮。

---

## 5. 關鍵發現

### (1) 瀕危物種的座標被「模糊化」到 ~30km 網格
山椒魚 293 筆中,座標不確定性中位數高達 **30,175m**,且高度集中(30175m 有 124 筆)。
這是**保育性座標 generalization** 的指紋——發布者刻意把座標降到約 0.25° 網格,避免被按圖索驥盜捕。
意義:**不清洗就拿 30km 精度的點去畫 1km 六角格,密度圖會是假的。**

### (2) GBIF Search API 有硬上限 → 強制 Download API
Search API:匿名公開、但 `offset` 上限 **100,000**、單次 300 筆。

| 類群(TW, 有座標) | 筆數 | 能否用 Search API |
|---|---|---|
| 無尾目 Anura | 545,877 | ✗ 超過上限 |
| 樹蛙科 Rhacophoridae | 189,852 | ✗ 超過上限 |
| 蟾蜍科 Bufonidae | 91,001 | ✓(勉強) |
| 黑眶蟾蜍 | 56,051 | ✓ |
| 艾氏樹蛙 | 11,165 | ✓ |

- **≤ 100k** → Search API 匿名搞定(**免帳號**)
- **> 100k 或要 DOI** → 必須用 **Download API**(需免費 GBIF 帳號、非同步、產出 DOI)
- 實測:11k 筆分頁 = 38 次請求、**273 秒**(~7s/次)。反證 18.9 萬筆絕不該用 Search API。

### (3) 常見種 vs 瀕危種,清洗結果天差地遠
艾氏樹蛙 11,160 筆只掉 2 筆 → 常見種**沒有**座標模糊化。對比山椒魚 80% 被降精度。

### (4) 不要把原始點丟瀏覽器 → 先 H3 聚合
艾氏樹蛙 11,158 點 → H3 res7 聚合成 **792 格**(14× 壓縮、檔案 5.7× 縮小)。
幾十萬點直接畫會卡死瀏覽器;伺服器端先聚合、只送結果,是 geodata engineering 的標準做法。

### (5) deck.gl UMD bundle 不含 h3-js(踩雷紀錄)
`deck.gl@9` 的 UMD scripting bundle **有 `H3HexagonLayer` 類別,卻沒打包 h3-js 依賴**,
執行 `new deck.H3HexagonLayer(...)` 會拋錯 → 整張圖靜默不渲染(底圖正常、但格子全消失)。
**修法**:
- 六角格邊界改在 Python 端用 `h3.cell_to_boundary()` 算好並 inline,前端用內建 `PolygonLayer`(`getPolygon`)畫,完全不需 h3-js。
- `MapboxOverlay({interleaved:false})`(overlaid 模式)讓 deck 畫在底圖**上層**,不被底圖填色蓋住。
- 驗證:無頭 Chrome `--headless=new --use-gl=angle --use-angle=swiftshader --virtual-time-budget=12000 --screenshot`(inline 資料的 deck 圖層即使底圖磚沒載到也會渲染)。

### (6) Mapbox vs MapLibre
deck.gl 是繪圖層,底圖引擎可換。Mapbox 底圖需 token;**MapLibre + CARTO 免費向量底圖**是零 token 的等效替代,視覺品質幾乎相同。「漂亮」來自 deck.gl 的 3D 擠出/光照/色階,不是 Mapbox 本身。

---

## 6. 檔案清單

| 檔案 | 用途 |
|---|---|
| `gbif_salamander.py` | 山椒魚:抓取 + 6 步清洗 + GeoJSON/pydeck |
| `salamander_hillshade.py` | 山椒魚:地形暈渲靜態圖(發文等級) |
| `gbif_anuran_h3.py` | 樹蛙(單種):分頁 + H3 聚合 + pydeck |
| `fetch_multi_anuran.py` | 樹蛙(多種):抓取 + 聚合成 `(hex,物種,年)` JSON |
| `build_deck_filter.py` | 產出物種下拉 + 年代滑桿的互動地圖 |
| `build_deck_maplibre.py` | 產出單種版 deck.gl + MapLibre 地圖 |
| `*.geojson` / `*.json` | 清洗/聚合後的資料(含 `fetched` 抓取日期) |
| `*.html` | 互動地圖(副標題標示資料更新日) |
| `salamander_hillshade.png` | 靜態暈渲圖 |
| `requirements.txt` | 相依套件 |
| `.github/workflows/update.yml` | 每月自動重建 + 部署 GitHub Pages |

---

## 7. 環境與執行

```bash
python3 -m venv .venv
.venv/bin/pip install pygbif pandas pydeck matplotlib contextily pyproj h3

# 山椒魚
.venv/bin/python gbif_salamander.py
.venv/bin/python salamander_hillshade.py

# 樹蛙(多種互動)
.venv/bin/python fetch_multi_anuran.py      # 抓取 ~15 分鐘,建議背景跑
.venv/bin/python build_deck_filter.py       # 產出 anuran_filter_map.html
```

互動 HTML 雙擊即可在瀏覽器開(需連網載 CDN 與底圖磚;資料已 inline,免本機伺服器)。

**API 版本備註**
- pygbif 0.6.6:`name_backbone(scientificName=, taxonRank=)`,回傳巢狀 `usage.key`(非舊版 `usageKey`)
- h3 v4:`latlng_to_cell()` / `cell_to_boundary()`(回傳 (lat,lng))

---

## 8. 發佈到網路(GitHub Pages,零伺服器)

架構是**靜態網頁 + 排程重建**:資料預先抓好、聚合、inline 進 HTML,訪客只開靜態檔,
**不需要常駐後端、不需要訪客即時連 GBIF**。資料更新交給 CI 排程。

**為什麼是「每月」**:GBIF 上游(iNaturalist 等)約**週級**更新,且一個月新增的觀測不會
肉眼改變熱區。月更是新鮮度與成本的甜蜜點;發文用的一次性快照則完全不必排程。

**一次性設定步驟**
1. 把專案 push 到 GitHub repo(公開 repo 的 Actions 免費)。
2. repo → Settings → Pages → Source 選 **GitHub Actions**。
3. 完成。`.github/workflows/update.yml` 會:
   - 每月 1 號(或手動 `workflow_dispatch`)跑 `fetch_multi_anuran.py` + `build_deck_filter.py`
   - 把 `anuran_filter_map.html` 放成 `public/index.html` 並部署到 Pages
4. 網址:`https://<帳號>.github.io/<repo>/`

**不要讓網頁前端即時抓 GBIF**:會失去伺服器端 H3 預聚合、大類群過不了 offset 上限、
每個訪客都觸發抓取對 GBIF 失禮。即時抓只適合「最近 7 天觀測」這種小 widget。

---

## 9. 待辦 / 下一步

- [ ] 高程過濾:疊 DEM,砍掉山椒魚資料中 < 1500m 的可疑點(誤鑑定)
- [ ] 走 Download API 跑全量樹蛙科(189k),取得 DOI(需 GBIF 帳號)
- [ ] 年份累積動畫(自動播放),適合做發文動圖
- [ ] 整篇打包成 Quarto 資料報導(山椒魚偵探故事 + 樹蛙互動圖)
- [ ] 大量資料改用 `tippecanoe` 切 PMTiles,讓十萬級資料在瀏覽器流暢跑
