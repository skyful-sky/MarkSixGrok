# EV-1 資料驗收：逐期銷量、獎項及來源

本輪完成資料收集、語義檢查及來源核對，**保留缺口，不啟動模型、選號、候選評分或預測**。依據 Manager 採納的 Astra 審查：`/workspace/research-duo/logs/codex-20261030T043345Z-bf91c494.jsonl` final。原 log 雜湊及先固定的期號／日期清單見 [acquisition-plan.json](../data/discovery/ev1/acquisition-plan.json)。

執行記帳在 [run-ledger.json](../data/discovery/ev1/run-ledger.json)，分類為資料驗收，新增命中嘗試0，累計仍14；不改既有 registry，不開 shadow ID。抓取時間為2026-10-30 UTC，逐一請求的起訖時間、方法、原始URL、最終URL、HTTP狀態及內容指紋保存在 [retrievals.json](../data/discovery/ev1/retrievals.json)。本輪取得2054份請求紀錄，沒有呼叫任何模型。

## 固定範圍及缺漏

UK採用 Astra 提案的701–1400；日本沿用既有 discovery 的701–1146，不跨1147期獎制界線補足500期；香港只取鎖定CSV已有的26/047–115。沒有取得或改寫正式26/116，也沒有開啟 `data/external` 封存結果。

| CSV | 期號／日期 | 期數 | 銷量NA | 財務NA格 | 其中無中獎者派彩不適用 | 其中來源衝突NA | 官方原公告時間NA |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [uk.csv](../data/discovery/ev1/uk.csv) | 701–1400；2002-09-11–2009-05-23 | 700 | 0 | 171 | 161 | 10 | 700 |
| [japan.csv](../data/discovery/ev1/japan.csv) | 701–1146；2012-10-11–2017-02-06 | 446 | 2 | 145 | 140 | 5 | 446 |
| [hongkong.csv](../data/discovery/ev1/hongkong.csv) | 26/047–115；2026-05-05–2026-10-27 | 69 | 0 | 47 | 47 | 0 | 69 |

「財務NA格」只計銷量、票價、各獎級中獎注數及實際每注派彩；不重計 `reported_prize` 副本或中繼資料。無人中獎的每注實際派彩記NA，理由為不適用，不能當成資料遺失或0元派彩。衝突NA包含上表兩個日本銷量NA。全部欄位的NA格總數（含中繼資料及報價副本）分別為2978、2071、254；逐欄統計在 [manifest.json](../data/discovery/ev1/manifest.json)。沒有刪期、補值、補期或延長窗口。

## 官方入口、替代來源與核對結果

### 英國 Lotto

[官方歷史入口](https://www.national-lottery.co.uk/results/lotto/draw-history)在 Astra 審查時遇403；本輪一般HTTPS GET實際回200，但內容只含近期紀錄，沒有目標701–1400期。[官方CSV入口](https://www.national-lottery.co.uk/results/lotto/draw-history/csv)轉向最新一期XML，沒有當成歷史CSV；[指定701期詳頁](https://www.national-lottery.co.uk/results/lotto/draw-details?drawNo=701)回500。HTTP200不代表已取得所需歷史範圍。

改用 [Merseyworld逐期檔案](https://lottery.merseyworld.com/archive/Lott701.html)，700頁均可解析印出的期號、日期、五級中獎注數／報價及主Lotto銷量；再以 [Lottery.co.uk逐期頁](https://www.lottery.co.uk/lotto/results-11-09-2002)核對全部700期五級獎項。Merseyworld稱其表格源自Camelot電話資料，但本輪沒有當年的官方原表，仍列第三方。兩站資料生成是否獨立未核實。

**700期銷量均只在Merseyworld取得，第二站未列銷量，故銷量未完成獨立交叉核對。** 只取主Lotto第一個獎項區塊的當期 `Ticket sales`，排除同頁HotPicks／Extra及Sat+Wed合計，沒有以獎金池、派彩或頭獎反推銷量。

五級中獎注數／實際派彩有8期、10個財務欄位衝突，列下表；計入報價副本共17條衝突紀錄。無人中獎時一站展示未頒出的頭獎報價、另一站顯示0，另列 `no_winner_quote_convention`，不當成實際派彩矛盾。

### 日本 Loto6

[瑞穗官方頁](https://www.mizuhobank.co.jp/takarakuji/check/loto/loto6/index.html)及歷史詳頁均為HTTP200動態空表。靜態閱讀其[官方顯示程式](https://www.mizuhobank.co.jp/common2024/js/transfer/lottery.js)後，找到頁面本來使用的逐期CSV，例如 [A1020701.CSV](https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/A1020701.CSV)。按官方程式的Loto6前綴及四位期號取得**全部446份官方CSV，均HTTP200**，以CP932解碼、NFKC正規化文字；逐份核對印出的期號與平成日期，保留五級獎項、銷量及獎級條件。

以 [loto6.jp列表JSON](https://loto6.jp/databases/resultlist/data?count=100&order=1&order_rule=2&view_order=1&view_type=1&stage=1&week=1&setball_type=1&offset=701)的5頁資料核對446期；`t1..t5`為中獎口數、`m1..m5`為每口金額、`sales`為銷售實績。找到5期、5個財務欄位差異；計入報價副本共7條衝突紀錄。官方原值及備用原值均保留，採納表暫記NA，供日後來源裁決；不按看似合理的數量級修正。官方「該当なし」明示無中獎者，中獎口數正規化為0；該級實際每口派彩NA。備用站的0元佔位另留，不冒充官方公告。

### 香港六合彩

[馬會結果頁](https://bet.hkjc.com/ch/marksix/results)只有JavaScript提示。靜態核對[官網bundle](https://bet.hkjc.com/static/js/main.5709b251.js)的 `marksixResult`／`lotteryDrawsFragment`，用其查詢向官方 `https://info.cld.hkjc.com/graphql/base/` 請求。GET回400 `BAD_REQUEST`；整段20260505–20261027的POST回200空陣列。改為六個按月日期窗口POST後，**取得69/69期 `status=Result` 的官方結果**。全部請求JSON、回應及雜湊均保留；空陣列沒有被解讀為無攪珠。

`lotteryPool.totalInvestment`為總投注額，`unitBet=10`為全注單位；**官方 `lotteryPrizes.winningUnit` 依官網顯示程式除以 `unitBet`，才是表上中獎注數**，保留小數，不取整、不視為獨立人數。例如26/047三獎原值1345÷10＝134.5注；每注派彩25,810元。[hk-unit-normalization.json](../data/discovery/ev1/hk-unit-normalization.json)逐期保存原值及換算依據。

以 [MarkSixInfo](https://marksixinfo.com/draw/26-47)核對69期銷量及七級獎項，另以 [lottery.hk](https://lottery.hk/en/mark-six/results/2026-05-05)核對66期；兩組均與官方的可比較財務欄位一致，沒有數值衝突。lottery.hk第26/108、113、115期雖HTTP200，實為「unusual traffic」CAPTCHA，明記未取得資料，沒有繞過。這3期仍有官方與MarkSixInfo兩個來源核對；沒有因CAPTCHA借用別期。第三方是否互相轉錄未核實。

MarkSixInfo的 `datePublished` 只有日期且為該站自報，另存 `secondary_claimed_publication_date`。沒有提升為官方、精確或已由當年存檔證實的公告時間。

## 尚未裁決的財務差異

下表省略重複的 `reported_prize` 副本；所有24條衝突（含副本）詳見 [conflicts.csv](../data/discovery/ev1/conflicts.csv)，全部21372條逐欄比較見 [crosschecks.csv](../data/discovery/ev1/crosschecks.csv)。不以多數決改值，衝突只遮蓋該欄，原來源及其他已核對欄位均留存。

| 國家／期號 | 欄位 | 主來源 | 核對來源 | 採納值 |
| --- | --- | ---: | ---: | --- |
| UK740 | 二級派彩 | 227194 | 27194 | NA |
| UK832 | 五級注數 | 764751 | 765751 | NA |
| UK891 | 三級派彩 | 1098 | 1089 | NA |
| UK945 | 三級派彩 | 2803 | 2802 | NA |
| UK981 | 四級派彩 | 42 | 47 | NA |
| UK1058 | 頭獎注數／派彩 | 3／2562460 | 2／3843690 | 各NA |
| UK1171 | 頭獎注數／派彩 | 2／4206341 | 3／2804227 | 各NA |
| UK1351 | 二級派彩 | 39596 | 39356 | NA |
| 日本1061 | 銷量 | 1437670400 | 143770400 | NA |
| 日本1067 | 二級派彩 | 8857400 | 8857300 | NA |
| 日本1117 | 銷量 | 1705685400 | 1795685400 | NA |
| 日本1132 | 四級派彩 | 11000 | 1100 | NA |
| 日本1145 | 五級注數 | 192292 | 19292 | NA |

## 票價、獎制及公告時間的證據界限

- UK列每注GBP1：[英國政府存放的2014年市場報告](https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/322845/report313.pdf)註24明載Lotto票價在2013年10月以前為1鎊，與[第三方制度史](https://www.lottery.co.uk/lotto/history)交叉佐證。窗口早於2013年改價及2015年矩陣變更；沒有混入2026年雙Round。五級命中條件及當期報價逐頁保存；未取得完整適用於每期的歷史獎金分配、封頂、特別獎／促銷版本鏈，`full_prize_rule_version=NA`。Merseyworld現行「Prize Structure」頁明指2013年制度，**沒有套用到2002–2009年**。
- 日本列每口JPY200：[協議會2011年寶ニュース764號](https://www.takarakuji-official.jp/news/pdf/764.pdf)為歷史官方定價證據，與[瑞穗商品頁](https://www.mizuhobank.co.jp/takarakuji/products/loto6/index.html)核對。這是文獻所載制度票價，並非每期CSV另列票價、亦非完整改價事件台帳。五級條件取各期官方CSV。[售票銀行2016年公告](https://www.japannetbank.co.jp/news/general2016/161226.html)明列1146期以前與1147期起的獎金差異，窗口止於1146；未把現行6億上限套到舊期。完整法定分配版本仍NA。
- 香港每注HKD10取官方逐期 `unitBet`，並核對[馬會投注資料](https://is.hkjc.com/AOSBS/help/ch/MK6_Guide.html)：六正選加特別號、七級條件、2024-05-21起的分配說明。另留[2026-03-30獎券規例](https://special.hkjc.com/e-win/en-US/betting-info/marksix/lotteries-rules/-/media/Sites/JCBW/Special/betting-rules/Lotteries_Rule_2_Eng_20260330)供審計；未取得逐期促銷／調整的完整版本鏈，故不把現行規則等同全期法律契約已核畢。
- **1215期官方原公告精確時間全部NA。** 開獎日期、停售／開售時間、HTTP `Date`／`Last-Modified`、頁面重建時間及本次下載UTC均不能代替原發佈時間。官方最新頁面的「更新日」也不證明歷史各期首次公告時刻。沒有倒填時間，沒有取得當年不可變存檔的聲稱。

本輪只驗收已公布的事後銷量／派彩資料；這些值不能作同一期投注前已知特徵，亦不能以本次下載證明當年投注前已可得。英日制度／玩家係數是否可轉用香港不在本輪範圍。資料雖已留存，原公告時刻、英國銷量第二來源、英日13期衝突及完整歷史規則鏈仍需覆核，`eligible_for_modeling=false`；本文件不授權進入任何EV模型或評分。

## 檔案與驗證

三份國家CSV以一期一列保存；[schema.json](../data/discovery/ev1/schema.json)解釋貨幣、全注等值、NA及各欄位。`primary_source_sha256`為原HTTP entity內容位元組在解碼／正規化前的SHA-256。`raw/target-sources.jsonl.gz`留每個採用／核對來源的原始回應；`raw/access-evidence.jsonl.gz`留官方程式、規則及接入證據。非目標結果頁只存明示的metadata投影，`stored_body_sha256`與原始回應SHA分開，沒有把投影冒作原文。

`prepare_ev1.py`只作離線解析，讀固定plan及本輪下載目錄，不讀封存窗口；輸出目錄已存在時拒絕覆寫。完整採集請求可按 `retrievals.json` 的GET URL／POST request JSON追查，沒有下載或執行外部模型。測試核對固定期號、NA統計、來源／檔案雜湊、原始回應重解析、官方日文無人中獎語義、HK小數注數換算、CAPTCHA辨識及衝突NA；不作候選評分。

文件側附 `.sha256`，資料目錄含 `SHA256SUMS` 及逐檔校驗。使用禁止封存結果讀取的全套測試profile；既有27項會讀封存結果的測試明示跳過，其他測試及本輪新測試均須通過。保護檔Git物件與tag參照存於 `protected-state.json`，提交前另核對與基線無差異。
