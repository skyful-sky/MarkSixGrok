# 26/047 起的官方物理資料來源審計

查核日期：2026-10-29 HKT；本輪實際網路查核約 11:33–11:36 UTC（19:33–19:36 HKT），基準 commit `ac1e4f3bc268dfbffe8342c8343023ad84017e3b`。範圍為已凍結的 **26/047–26/115，69 期，2026-05-05–2026-10-27**；26/116 不納入歷史資料審計或評分。

**官方六合彩直播及一般攪珠程序資料可核實，但本輪未取得這 69 期任何一期已核驗的物理出球次序、球組 ID 或機器編號。三項逐期欄位皆為「缺」，目前不足以據此建立需要這些欄位的方法。**「不可得」在本文指本次經列明公開途徑未取得，不是斷言馬會沒有保存、從未公開或日後不能取得。本次也沒有逐一播放 69 段影片，不把搜尋無結果當作全庫不存在的證明。

## 欄位可得性與逐期覆蓋

| 欄位／資料 | 可得性（本輪） | 來源 URL | 已核驗可追溯期數 | 缺口 |
|---|---|---|---|---|
| 物理第 1–6 球次序；若需要則連第 7 球 | **不可得**；直播渠道可得，完整歷史逐球紀錄未取得 | [HKJC TV](https://campaign.hkjc.com/ch/jctv/)、[官方結果頁](https://bet.hkjc.com/ch/marksix/results) | **0/69**；26/047–115 全段未補入次序 | 官方逐期影片／有序表、期號與日期對應、連續逐球片段、時間定位及可核驗轉錄均缺 |
| 每期使用球組（ball set）ID | **不可得**；只有一般抽選球箱程序可核實 | [馬會 2016-02-19 程序公告](https://www.hkjc.com/chinese/pressrelease/mcs01_showhtml.asp?SelType=NEWS&filename=20160219_143108_C_NEWS.htm) | **0/69** | 逐期抽選結果、球箱／球組的穩定識別、換組及沿用紀錄、公開可用時間均缺 |
| 每期實際攪珠機編號 | **不可得**；代際公告僅部分背景資料可得 | [馬會 2026-04-21 公告](https://corporate.hkjc.com/zh-HK/news-and-publications/corporate-news/2026-04/news_2026042101511)、上述程序公告 | **0/69** | 逐期機器序號／穩定 ID、主機與後備機對應及實際使用紀錄缺；「第五代」不是機器編號 |
| 官方影片渠道與示範片（輔助） | **部分** | [HKJC TV 介紹](https://campaign.hkjc.com/ch/jctv/)、[頁面連結的示範 MP4](https://streaminghkjc-a.akamaihd.net/hdflash/jctv2/marksixClip/marksix_2.mp4) | 目標 69 期已驗證重播 **0** | 示範片可讀，不含已核實的目標期號；公開歷史清單、留存範圍、每期完整影片缺 |
| 機器代際及一般流程（輔助） | **部分** | 2026-04-21 代際公告、2016-02-19 程序公告 | 一般公告，不算逐期識別覆蓋 | 不能把公告自動展開成 69 筆相同球組或同一部機器紀錄 |

[逐期缺口清單](review-evidence/data-source-coverage.csv)逐列列出 69 個期號及原快照日期，三項欄位和已核驗官方逐期來源一律寫「缺」。日期只用來界定本庫審計範圍，未冒稱本次已逐列向官方重驗。0/69 是取得並核驗的紀錄數，不是機制成功／失敗率，更不是回測結果。

## 實際上網查核與來源界限

### 1. HKJC TV 官方直播與影片

[HKJC TV 官方介紹及 FAQ](https://campaign.hkjc.com/ch/jctv/)實際 GET 為 HTTP 200。頁面確認六合彩直播由馬會提供，於節目開始前約五分鐘出現播放入口；六合彩欄列直播、下期資訊和攪珠結果。這能證實官方直播途徑，不能證實任意歷史期次皆可重播，亦不能把賽馬節目的重溫功能套到六合彩。

`https://www.hkjc.com/jctv/` 本次回應是指向 `//campaign.hkjc.com/ch/jctv/index.aspx` 的 HTML meta refresh；已另行讀取 campaign 內容，沒有把空殼／轉向頁誤判為影片不存在。

介紹頁的 `marksixTab1-lg` 實際連結上述 `marksix_2.mp4` 示範片。HEAD／GET 均 200，GET 973,390 bytes，SHA-256 `a555131dbad96bb801ed5df3b82204fad80929ed56a77e4424178e3040c52c43`；ffprobe 時長約 10.164792 秒。第 4 秒畫面是手機直播介面內的攪珠室，未核實對應 26/047–115 任一期，故沒有轉錄或採用球號、球組或機器編號。HTTP Last-Modified 為 2016-03-22，媒體自載 creation_time 為 2015-11-23；兩者均不是目標期次或可信拍攝時間證明。影片原檔僅用暫存檔查核，未存入正式資料或出票程式。

[50 週年官方專頁](https://campaigns.hkjc.com/2026-marksix/ch/)直接 GET 成功，頁面連往 [HKJC YouTube](https://www.youtube.com/user/HKJC/playlists)；但本次讀取 YouTube 播放清單只取得頁尾，沒有取回目標期次的可驗證清單。該專頁經 web 閱讀工具回 403，與直接 GET 200 的結果分別保留，不合併成「完全不可連線」。[官方流動服務指南 PDF](https://m.hkjc.com/download/DigitalGuide_HKJC_chi.pdf)經 web 工具因 27,092,775 bytes 大小限制未能全文讀取；搜尋摘要不作完整歷史覆蓋證據。

搜尋亦找到 [26/047 第三方 YouTube 重播](https://www.youtube.com/watch?v=iJLQDwxiz1Q)，上載者為「六合彩頭獎貓」，說明自稱摘錄 HKJC app。它是未經本輪認證的轉載線索，**不是馬會官方帳號或已核驗官方原檔**；沒有採用其逐球值。頻道名稱或字幕出現「HKJC」亦不足以認定官方來源。未核對授權、剪接與連續性之前，不填進官方逐期清單。

### 2. 官方結果頁、現行 query 與舊介面

[官方結果頁](https://bet.hkjc.com/ch/marksix/results)直接 GET 成功，但 HTML 是 JavaScript 應用外殼；web 文字讀取只得啟用 JavaScript 提示。本次重取其 [主 bundle](https://bet.hkjc.com/static/js/main.5709b251.js)，`lotteryDrawsFragment` 選取期號／日期及 `drawResult { drawnNo xDrawnNo }`，未另選有序逐球、球組或機器 ID 欄位。這只描述被檢視的 query，不是完整 schema 稽核，也沒有證明 `drawnNo` 的陣列次序就是物理次序。

本次依[既有介面審計](data-fields-likelihood.md)所存 query 重新請求 `https://info.cld.hkjc.com/graphql/base-get/`，日期 20260505–20261027、lastNDraw=100，HTTP **400**，原文 `{"errors":[{"message":"Internal server error - BAD_REQUEST"}]}`。沒有得到可用歷史回應；不能由這次失敗推斷 API 完全沒有相關欄位。

另實際檢查外部項目曾使用的官方舊 URL `https://bet.hkjc.com/contentserver/jcbw/cmc/last30draw.json`，本次 HTTP **404**，回傳應用 HTML 而非 JSON，沒有讀到逐期次序。沒有把回傳外殼當成成功取得資料。

本庫 `marksix_data.csv` 的六正選是升序集合；**升序第 1 欄不等於第 1 個物理出球**。[官方投注指南](https://is.hkjc.com/AOSBS/help/ch/MK6_Guide.html)區分先六球與第七特別號，但沒有提供本審計所需的 69 期逐球表。本文未新增任何次序估計或回填。

### 3. 球組與機器的官方公開資訊

[2016-02-19 官方公告](https://www.hkjc.com/chinese/pressrelease/mcs01_showhtml.asp?SelType=NEWS&filename=20160219_143108_C_NEWS.htm)可讀，記述抽選球箱、嘉賓檢查及簽名、攪珠後上鎖與定期檢查。文中的攪珠前檢查排列，**不是某期的物理出球次序**。這是較早的一般流程描述；沒有逐期球組／機器 ID 表，亦不能據此認定 2026 年每期使用哪組實體球或哪部機器。

[2026-04-21 官方公告](https://corporate.hkjc.com/zh-HK/news-and-publications/corporate-news/2026-04/news_2026042101511)確認第四代在 5 月 2 日週年攪珠後退役，隨後採用第五代。這是可核實的代際轉換背景，沒有實體序號與 26/047–115 的逐期使用對照。外觀、顏色、同代型號或前一期號碼均不能代替球組／機器識別；本輪不據此推測磨耗或跨期沿用。

本次沒有取得 69 期抽選表、監場簽署紀錄或換機／換組台帳的公開原檔，也沒有聯絡馬會或代表 Manager 發送資料要求。若日後取得，可另記官方 URL、期號／日期、明確欄位語義、原檔雜湊及首次可用時間，區分事前／事後資料，再驗證覆蓋與缺口；**這是資料驗收要求，不是恢復已解除的研究暫停條款**。

## 證據、交付與限制

本輪 HTTP 狀態、抓取時間、原始回應雜湊、影片查核、搜尋字串及失敗原文保存在 [data-source-audit.json](review-evidence/data-source-audit.json)。未把原始官方網頁全文存入本庫；指紋只代表此次取得的回應，不能倒推歷史公開時間。舊介面審計證據保留原狀，本文件補充實際新查核。

A19 的兩份原始 log 已逐位元組附於 [review-evidence/a19/](review-evidence/a19/)，詳見 [lessons.md](lessons.md)。一般流程可得與逐期欄位不足並存；沒有資料不等於否定機制，也不等於本輪有合格模型提案。

本輪新增 **0 ID、0 attempt**，仍 **14/20，剩 6**。不回測、不調整停用族；H3／prereg-r2／prereg-r3、固定 CSV、兩份 26/116 預測、所有出票程式及 registry 不動。測試命令為 `PYTHONDONTWRITEBYTECODE=1 /tmp/marksix-r2-venv/bin/python -m pytest tests/ docs/review-evidence/test_signal_visibility_diag.py -q -p no:cacheprovider`；結果 **96 passed in 6.85s**，全綠。

本文件 SHA-256 見 [同名校驗檔](data-source-audit.md.sha256)；各新證據與 lessons 的雜湊納入 [review-evidence/SHA256SUMS](review-evidence/SHA256SUMS)，由庫根執行 `sha256sum --check docs/review-evidence/SHA256SUMS`。
