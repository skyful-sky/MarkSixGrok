# UK／日本球組與機台資料來源審計

本輪只收集及核對資料，沒有模型、候選、回測、分佈分析或預測，累計嘗試仍14次（現行無上限）。基準為`6aa42ec448e03f55d8b01f8c675e69e470980fbd`。實際HTTP取得時間為2026-10-29 23:40–23:45 UTC；逐次精確時間、要求URL、最終URL、狀態、原始HTTP內容SHA-256及保存內容SHA-256見[data/discovery/apparatus/retrievals.json](../data/discovery/apparatus/retrievals.json)。下載時間不能倒推歷史首次公開時間，也不代表截止投注前已可得。

## 資料及隔離

| 新檔案（均在`data/discovery/apparatus/`） | 期次／日期 | 缺口及採納欄位 |
|---|---|---|
| `uk-lotto-701-1400-apparatus.csv` | 701–1400，共700期；2002-09-11–2009-05-23 | 缺期0；機台700期一致；球組699期一致，第1322期衝突記NA |
| `japan-loto6-all-setballs.csv` | 1–2150，共2150期；2000-10-05–2026-10-29 | 缺期0；2125期採納球組，24期跨站衝突＋1期來源重複期號衝突，25期NA；各站原值另列 |
| `japan-loto6-701-onwards-draw-order.csv` | 701–2150，共1450期；2012-10-11–2026-10-29 | 927期兩站一致；520期只有一站可核；1519、1758、2007三期採納值NA |

日本「全部期數」只固定至取得時已完成的第2150期，不含第2151期空白預告。為維持封存隔離，第1–700期只保存日期、球組及來源類別ID，**不保存其球號／出球次序**；loto6.jp的前七頁回應及hpfree第1–75期頁在保存前移除結果欄位，原始回應雜湊另留。這是刻意保留的次序覆蓋缺口，不能把1–700期當成無紀錄。未開啟`data/external/`封存結果，亦未改該目錄任何檔案。

新資料不併入四份既有discovery結果CSV，既有`access.py`不接受新資料鍵，校準、出票及評分程式不變。日本全期球組表含早於／晚於既有探索區間的中繼資料，不能自動作現有探索集的擴充；也不能據此聲稱舊窗口重新未曝光。兩個`raw/*.jsonl.gz`只供來源審計，不是探索輸入。每行為`key`與原文base64；使用`retrievals.json`的`bundle_key`追溯。被投影的頁面明列`content_projection`，**保存內容不冒作完整原始HTTP回應**。

## UK：欄位對應、逐期交叉核對與雙Round排除

主要來源為[Merseyworld CSV格式頁](https://lottery.merseyworld.com/cgi-bin/lottery?days=2&Machine=Z&Ballset=0&order=0&show=1&year=0&display=CSV)，[篩選介面](https://lottery.merseyworld.com/Winning_index.html)明列Machine、Ball set及Drawn／Ascending。表頭的`Machine`對應操作名稱（例如Merlin），`Set`對應球組標籤（例如3）；不按最後兩欄的固定位置取值。保留實際表頭及新範圍的中繼資料投影，丟棄所有球號及窗口外行。

第二來源為Lottery.co.uk每期詳頁，例如[701期](https://www.lottery.co.uk/lotto/results-11-09-2002)及[1322期](https://www.lottery.co.uk/lotto/results-23-08-2008)。700頁均HTTP200；逐頁核對印出的draw number，以既有`data/discovery/uk.csv`的期號／日期作對齊，不重編索引。`Ball Machine Used:`及`Ball Set Used:`分別與Merseyworld名稱及球組比較，保留兩站原值。結果：機台700/700一致；球組699/700一致。第1322期兩站均Sapphire，但球組分別1及5，故`ball_set=NA`；[Results.co.uk同日頁](https://www.results.co.uk/lotto-result-2008-08-23)作額外線索留存，未據此多數決或宣稱獨立第三來源。沒有取得官方逐期原表，衝突未解。

已實際要求[官方CSV入口](https://www.national-lottery.co.uk/results/lotto/draw-history/csv)，它轉向`/results/lotto/draw-history/xml`，只回第3219期／2026-10-28最新資料，含多個`draw-machine`與`balls`節點；未當成歷史CSV或與700期合併。**本輪未取得當年官方CSV，不能核實歷次球組／機台欄位調換發生時間，也不能聲稱已修正官方原表。** 本輪用清楚的表頭與逐期語義標籤交叉核對，避免直接沿用官方CSV的欄位置。

Merseyworld下載內容中，所有年分≥2026的127行（含雙Round）均在投影前丟棄；另排除其餘窗口外行。目標701–1400每期只有一行，日期遠早於2026。官方最新XML僅作不適用來源的審計證據，不作歷史資料；不從它推定兩機器節點與兩Round的實體對應。

`machine`是來源的操作名稱，`ball_set`是操作標籤，均不是已核實的製造序號。窗口內見Arthur等舊名稱與Amethyst等新名稱；[id-history.json](../data/discovery/apparatus/id-history.json)逐一列出13個機台、11個球組標籤在**本窗口內**的首次／末次觀測。這些邊界不是出廠、換機、換球、改名或退役日期，不能把同一數字球組視為全程同一批實體球。[LotteryGen背景頁](https://www.lotterygen.co.uk/machine_page.html)稱2003年起換用新機器，但不是官方完整台帳，不把其說法回填成逐期實體ID。[英國監管者FOI答覆](https://www.gamblingcommission.gov.uk/about-us/freedomofinformation/print/physical-draw-equipment)對1994–2001相關器材紀錄稱未持有；它早於本窗口，不能推出2002–2009的更換紀錄不存在。**窗口內完整更換／重編台帳及實體ID穩定性仍未核實。**

## 日本：三個全期來源、補充來源及差異處理

| 來源 | 取得及欄位 | 可解析有效A–J期數 |
|---|---|---|
| [tatuo全期表](https://tatuo.net/set/data.php) | 每50格的明列期號範圍，每格一個SET；空格保留原槽位 | 2149/2150；1880空白 |
| [loto6.jp列表介面](https://loto6.jp/databases/resultlist)及[JSON例頁](https://loto6.jp/databases/resultlist/data?count=100&order=1&order_rule=2&view_order=2&view_type=1&stage=1&week=1&setball_type=1&offset=701) | 22頁，按明列`id`、`date`、`setball`；保留`stage_id`及`setball_id` | 2150/2150 |
| [umiduki](https://umiduki.net/loto6/ranku/set.php) | POST表單`dete1=2150&dete3=2150&K01=100`實際回全期表；按各列印出的起訖期號讀取，非按要求參數假定範圍 | 2144/2150；6格空白或非A–J |
| [PSSH​C全期頁](https://www.psshc.org/dates/sets/%E9%81%8E%E5%8E%BB%E3%81%AE%E5%85%A8%E3%82%BB%E3%83%83%E3%83%88%E7%90%83%E4%B8%80%E8%A6%A7/) | 印出期號與緊接圖片alt標籤 | 1250期有效；實際覆蓋770–2024部分，並非全期 |
| [hpfree摘出順頁](https://www.hpfree.com/takarakuji/pulls-actually-loto6.html)及其三個歷史連結 | `セット球`及第1–6個／B數字，區分正式表與空白預告 | 1000期標籤有效；另1758期重複且值衝突 |

以tatuo與至少兩個完整範圍來源（loto6.jp、umiduki）交叉核對，再納入PSSH​C／hpfree可得列；**不同網域不代表資料生成獨立**，尚未核實各站是否互相轉錄，尤其tatuo與umiduki有相同差異。所有來源均屬非官方，沒有升格成官方逐球驗證。

採納規則：保存原值；僅作Unicode NFKC及英文字母大寫正規化，非A–J記NA；至少兩個有效來源且所有有效來源一致才採納；任何有效值相衝或同站重複期號值相衝，採納值NA。沒有以多數決選值、刪期、補期或重命名。有25期採納球組NA，完整期號清單在manifest；24期跨站差異，例如2149期tatuo／umiduki=A、loto6.jp／hpfree=J；另外hpfree把兩筆不同內容都印作1758期，保持來源錯誤，不猜其中一筆應是哪期。PSSH​C印作12923的行排除，不猜成1292或1923；其標題為早期球組範圍的另兩頁，實際內容為後來期號，未按頁名回填早期。sougaku兩個HTTPS網域均憑證主機名不符、HTTP入口回500，保留失敗紀錄，沒有停用憑證驗證繞過。

### 出球次序及ID更換

loto6.jp介面`view_order=2`明標「抽選順」，所載[顯示程式](https://loto6.jp/js/resultlist.js?v=20231124)使用`o1`–`o6`，一般升序顯示則用`n1`–`n6`；B數字是`nbo`。本輪只靜態讀取程式確認語義，沒有執行該站程式。新次序表只收701–2150；每列檢查六個o欄是六個n欄的排列，B不在六正選中。**排列一致只驗內容，不能證明物理次序真確。** hpfree的`1個目`–`6個目`、`B数字`作第二來源；927期順序一致，520期單站記錄明標`single_nonofficial_source`，1519及2007期兩站個別位置不同、1758期同站重複，三期採納次序與B全列NA。不是把升序欄冒充次序，亦未以此建立任何似然候選。

[球組解說站](https://www.loto6.info/?page_id=576)報東京138期／2003-06-05、649期／2012-04-12、1367期／2019-04-01換代；另報大阪336期開始、944期／2015-02-23及1768期／2023-02-20換球。[hpfree](https://www.hpfree.com/takarakuji/pulls-actually-loto6.html)也提大阪1768起新色。期號／日期與loto6.jp來源相符，詳列`id-history.json`，但**更換事件只屬第三方記述，未得官方台帳確認**。東京／大阪及不同世代重用A–J，解說站亦指出同字母有後備組；`setball_id`的1–10與`stage_id`都是網站類別，非實體序號。採納表的`physical_set_id`／`machine_id`全為NA，不能認定球組ID跨期穩定，也不靠名稱推定未記載更換。

## 香港：截止投注前的公開可得性

結論：**未見官方公開「每期實際球組ID／攪珠機序號」且可核證早於截止投注的資料。** 這是本輪列明來源的查核結論，不是斷言官方永不公布。

重新實取[馬會規例目錄](https://www.hkjc.com/chinese/betting/betting_rule.aspx)、[獎券一般規例](https://www.hkjc.com/chinese/betting/template_betting_rule_files/pdf_ch/Lotteries_Rule_2_Chi_20260330.pdf)及[六合彩獎券章](https://www.hkjc.com/chinese/betting/template_betting_rule_files/pdf_ch/Lotteries_Rule_3_Chi.pdf)。一般規例2.3由營辦者決定攪珠方法／時間／地點，2.5(a)提開始出售前公告運作形式，2.15提記錄攪珠結果及獎金；所查章節沒有逐期球組或機台序號的事前公開欄位或時間承諾。「公告運作形式」不能代換成「公告本期實體球組」。

[2016-02-19官方流程公告](https://www.hkjc.com/chinese/pressrelease/mcs01_showhtml.asp?SelType=NEWS&filename=20160219_143108_C_NEWS.htm)描述嘉賓在攪珠前抽選球箱及兩部機器一主一備，未給逐期ID，也沒有說球箱選定早於截止投注並向外公開。[2026-04-21官方公告](https://corporate.hkjc.com/zh-HK/news-and-publications/corporate-news/2026-04/news_2026042101511)事先宣告第四代於5月2日後退役、隨後用第五代：**機器代際的一般預告確實存在**，不能擴大為每期球組或實際機台序號已可事前取得。另取[投注指南](https://is.hkjc.com/AOSBS/help/ch/MK6_Guide.html)及[六合彩入口](https://bet.hkjc.com/ch/marksix)，後者只得JavaScript外殼，不能以外殼未載欄位證明完整服務沒有該資料。全部HTTP證據和缺口保留，未發送查詢訊息或推測ID。

## 重現、校驗與保護範圍

離線解析器為[`prepare_apparatus.py`](review-evidence/prepare_apparatus.py)，只讀新審計包及原discovery UK對齊資料，不接觸封存結果，不含評分。入口拒絕覆寫已有新CSV；測試在記憶體重新解析，核對輸出位元組，沒有重跑校準。

manifest列出三個資料表、證據包和取得台帳SHA-256；各檔另附`.sha256`，總目錄`data/discovery/SHA256SUMS`及子目錄`SHA256SUMS`包含新檔。原有discovery結果CSV、manifest與存取模組內容不變；H3、兩份prereg、正式26/116、META、`marksix_data.csv`、registry、全部既有tag及`data/external/`均不改。

測試採`--no-sealed-results`完整收集模式：已知需讀封存結果的27個舊完整性案例明確跳過，其餘全部執行；新增測試查來源雜湊、固定槽位、日期／期號對齊、欄位移位、雙Round排除、差異NA、次序語義及封存隔離。確切結果載於交付回報。
