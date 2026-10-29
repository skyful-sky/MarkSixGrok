# 外部固定窗口與欄位級來源合格清單

本輪基準 `c7303326f77e838cc7b9bf8fff11b182fd8b03e2`；查核日期 2026-10-29 HKT。補充[外部預驗證協議](external-validation-protocol.md)，不改200／500、八注映射、公平基準、α、通過／停止條件。**初版只鎖定窗口中繼資料；本輪已補備用歷史快照，仍不代表合格、未曝光holdout，四個彩票均不能據此開跑候選。**沒有候選評分、回測、新ID、外部提交序號或香港attempt。

## 本輪下載複核（基準2984885之後）

四組各700期的六主號、獨立額外球及日期已從原列備用站取得，存於[`data/external/`](../data/external/README.md)。**備用快照的700列／200暖身＋500評分、無重複、無主號缺漏、期號或期序及固定邊界已核實**；每列有URL與原文路徑，全部成功回應保存原文及SHA-256。UK期號為日期排序索引，僅四個邊界詳頁印出期號已另核，不冒稱每列皆有官方期號。

日本完整700列備用球組及報稱抽選順序已取得；所有彩票的**官方完整逐期對照、完整歷史矩陣／機球制度及未曝光資格仍未核實**。UK官方CSV本輪回200但轉為最新期XML，非目標歷史；日／中官方歷史403，韓官方JSON SSL EOF。本輪已下載與解析全部結果，不能聲稱盲測資格。逐項判定、來源與資料雜湊以[下載審計](external-data-download-audit.md)及[manifest](../data/external/manifest.json)為準；下列窗口定義不變，首版HTTP狀態保留作當時記錄。

## 選窗規則：不看任何候選成績

統一採**自原遊戲首期起最早的700期原始主攪珠**：第1–200期暖身，第201–700期評分，再按原協議固定切成五段各100期。這項選擇只用上市／首期、原始期號及日期，不用球號頻率、勝期、機制p值或模型成績；不因抓取困難、缺期、制度疑點或結果不利移到另一段。這落實本次任務引用A8／A13的不挑有利時段要求，A13原有同注／不同注子集的完整呈報亦保留。

UK只列已核實的歷史6/49遊戲；不混Lotto Extra、Big Draw、raffle或現行59球制度。跨年重設期號的雙色球按實際列表累計，**不得用年份期號相減或每年假設固定期數**。日曆日期不等於期次，休市／改期亦不以固定七天推填。

窗口在任何本庫候選評分之前固定，完整機讀定義見 [external-holdout-windows.json](review-evidence/external-holdout-windows.json)，其UTC鎖定時間是本輪本機記錄，公開可核證版本以本次提交為準。來源頁含歷史號碼／摘要，本輪核對時部分內容已可見；**不能聲稱研究者從未看過**。四組均保留 `no_prior_exposure_verified=false`，未取得獨立保管／未參與選模證據前，不能作原協議的確認性申請閘門；不能靠新切窗口或多重比較校正消除已曝光問題。

## 固定期號與當地日期

所有日期是當地開獎日，不是擷取／公開提交時間。表中「備用核對」只證明在該來源讀到對應日期，**不等於官方逐期重驗合格**。

| 彩票 | 暖身200期：確切期號／日期 | 向前評分500期：確切期號／日期 | 邊界證據與待核項 |
|---|---|---|---|
| UK歷史Lotto 6/49，Europe/London | **1–200**；**1994-11-19–1997-11-22** | **201–700**；**1997-11-26–2002-09-07** | 首日由[英國國會](https://publications.parliament.uk/pa/cm200304/cmselect/cmcumeds/196/19605.htm)核對；[1](https://www.results.co.uk/lotto-result-1994-11-19)、[200](https://www.results.co.uk/lotto-result-1997-11-22)、[201](https://www.results.co.uk/lotto-result-1997-11-26)、[700](https://www.results.co.uk/lotto-result-2002-09-07)期號／日期在備用站核對。官方完整700期原檔：**未核實**。 |
| 日本Loto6，Asia/Tokyo | **1–200**；**2000-10-05–2004-08-19** | **201–700**；**2004-08-26–2012-10-08** | [第1期](https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/loto60001.html)、[第200期](https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/loto60181.html)、[第201期](https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/loto60201.html)日期已從瑞穗核對；[700期](https://loto6.jp/databases/resultsearch/700)由備用站核對。官方700期及整段原檔：**未核實**。 |
| 韓國Lotto6/45，Asia/Seoul | **1–200**；**2002-12-07–2006-09-30** | **201–700**；**2006-10-07–2016-04-30** | [備用首期歷史表](https://lottostory.kr/guide/history/)、[200／201期年表](https://lottohaebom.com/history/2006)、[700期](https://kr.lottolyzer.com/home/south-korea/6_slash_45-lotto/detail-view/draw/700)核對。政府[十週年介紹](https://www.korea.kr/briefing/policyBriefingView.do?newsId=148753767)也記2002-12-07起步，但不能代替逐期結果。官方邊界／整段原檔：**未核實**。 |
| 中國雙色球紅球，Asia/Shanghai | **2003001–2004111**；**2003-02-23–2004-12-05**；累計第1–200期 | **2004112–2008029**；**2004-12-07–2008-03-13**；累計第201–700期 | [500.com備用原表](https://datachart.500.com/ssq/history/newinc/history.php?start=03001&end=08029)實際讀到700列期號／日期；[江蘇福彩紀錄](https://www.jslottery.com/articles/b650d8e3-48df-4c9c-81e5-ea108b2b113c?locale=zh-CN)確認第700次在3月13日，[官方獎訊](https://www.jslottery.com/winning_info?locale=zh-CN&lottery_type_id=10&page=714)對應2008029／2008-03-13。官方完整700期原檔：**未核實**。 |

雙色球備用表的累計分母為：2003年89期＋2004年122期＋2005年153期＋2006年154期＋2007年153期＋2008年前29期＝700。暖身89＋111＝200；評分為2004年餘11＋153＋154＋153＋29＝500。前輪只含期號／日期的[700列中繼資料](review-evidence/external-ssq-issue-calendar.json)完整保留；本輪新增紅球快照與其逐列比對一致，沒有進行評分。

## 制度／矩陣分界：已核實與未核實分開

本表將**主號矩陣N、m**、抽獎頻率、獎金／價格及實體機球制度分開。只驗證六主號命中不等於證明所有操作條件相同；沒有查得變更不等於沒有變更。完整窗口的矩陣歷史與設備一致性均仍需正式資格核對，機讀檔明示未通過，不能以測試全綠取代官方證據。

| 彩票 | 已核實的規則／變更資料 | 精確日／缺口及本窗處理 |
|---|---|---|
| UK | [國會一手材料](https://publications.parliament.uk/pa/cm200001/cmselect/cmcumeds/56/5604.htm)明載歷史6/49；[當時提交國會的資料](https://publications.parliament.uk/pa/cm199900/cmselect/cmcumeds/958/0112302.htm)同載六取49。[國會](https://publications.parliament.uk/pa/cm200304/cmselect/cmcumeds/196/19605.htm)確認**1997-02-05**增加週三主攪珠；[監管年報](https://assets.publishing.service.gov.uk/media/5a80024a40f0b62305b889e8/Gambling_Commission_annual_report_and_accounts_2015_to_2016.pdf)確認**2015年10月**由49增至59。 | 矩陣改制的官方**日**未核實，不能把其他公告日期冒充。採保守政策從**2015-10-01起排除**，這是排除界線，不是聲稱實際改制日；本窗於2002年結束。頻率改變不改6/49基準，但不能據此宣稱機器未換。 |
| 日本 | [官方20週年回顧](https://www.takarakuji-official.jp/news/recent/?newsId=201106)確認**2011年4月**由每週一次改為兩次；現行[官方規則](https://www.takarakuji-official.jp/kuji/loto/loto6/)為6/43。 | 備用史料稱2011-04-04／第543期首次週一，本輪未取得官方精確日，標**未核實**；不將其推定為矩陣／機器變更。窗口跨頻率變化，保留註記；完整歷史矩陣／實體機球一致性：**未核實**。 |
| 韓國 | [官方介紹](https://www.dhlottery.co.kr/lt645/intro)為6/45，bonus獨立；本輪沒有取得完整歷史規則變更表。 | 矩陣變更日、價格／獎級／機器／球組歷史日期：**未核實**。不因當前規則及每週日期看似一致，就宣稱2002–2016完整制度已驗證。 |
| 雙色球紅球 | 現行[官方規則](https://www.scflcp.com.cn/yxgz/823145252.jhtml)為紅6/33、藍1/16。[財政部通知](https://www.mof.gov.cn/gp/xxgkml/zhs/200806/t20080624_2496540.htm)批准自**2004-07-26**調整為每週二、四、日。另[官方修規通知](https://www.szlottery.org/fcw/fcxw/tzgg/content/post_1649773.html)明載**2026-02-01／2026014**生效，位於本窗之外。 | 2004-07-26是通知批准起日，備用期表首次週二為2004-08-24／2004067，二者不可混稱實際落實日；官方實際首次週二仍**未核實**。完整2003–2008矩陣、早期額外藍球及設備制度：**未核實**，不以2026版規則倒推全部歷史。主指標只用紅球，仍不代表所有遊戲規則一致。 |

因此「制度一致」目前只能測試**登記的預期矩陣與已知切點不矛盾**，不能宣告全部官方歷史證據已齊。若候選需要星期／機球／操作制度同質性，還須依原協議另驗其事前資格；任何實際矩陣或所需機制變更出現在固定窗內，應記NA／中止，**不移窗補跑**。

## 欄位級來源合格清單

「合格」只限已核對的欄位；網站本身官方不代表每個歷史欄位都已取得。備用資料可核日期及發現缺口，未與官方逐期對齊前，不提升為合格模型輸入。

| 彩票 | 官方來源URL／已核範圍 | 備用來源與限制 | 球組／機號／物理落球次序 |
|---|---|---|---|
| UK | [營辦者歷史結果](https://www.national-lottery.co.uk/results/lotto/draw-history)／[CSV](https://www.national-lottery.co.uk/results/lotto/draw-history/csv)本輪403；上述國會與監管文獻合格用於歷史6/49、首日／頻率及2015月級分界，不能代替700期結果。 | [Results.co.uk](https://www.results.co.uk/lotto-result-1997-11-26)的邊界期號／日期可核；[Merseyworld CSV](https://lottery.merseyworld.com/Draws/CSV.html)403，僅列未取得備用線索。 | 部分備用結果頁列球組及機器名稱；只核得樣例欄位存在，**官方完整700期球組／機號未核實**。Merseyworld未取回，物理次序**未核實**；排序結果不能當出球序。 |
| 日本 | [瑞穗歷史入口](https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/index.html)及上表三個舊頁合格用於已讀的邊界日期／升序結果；官方產品頁合格用於當前6/43。舊700期頁403／讀取失敗；通用detail頁只回空表，不算成功取得。 | [loto6.jp／700期](https://loto6.jp/databases/resultsearch/700)可核日期；頁面有セット球及抽選順欄位，來源語義／正確性未與官方影片核實。 | **部分備用欄位可見**；官方球組、逐期機器ID及完整落球次序**未核實**。不把備用組別字母當機器ID，不把夢ロトくん型號當逐期序號。 |
| 韓國 | [官方結果入口](https://www.dhlottery.co.kr/lt645/winNumber)／[規則](https://www.dhlottery.co.kr/lt645/intro)；本輪舊JSON、舊byWin及帶期次的新頁直接請求均SSL EOF。可沿用已核當前6/45規則，不能聲稱取得歷史700期。 | [2006年備用期表](https://lottohaebom.com/history/2006)、[Lottolyzer700期](https://kr.lottolyzer.com/home/south-korea/6_slash_45-lotto/detail-view/draw/700)只按已讀欄位分級；未自動批准全部年表。 | 官方球組／機號／落球次序**未核實**；直播渠道或bonus欄存在，不等於歷史序列已取得。 |
| 雙色球 | [中福彩歷史入口](https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/)／[公開查詢端點](https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice)本輪查2003001–2009001回403；江蘇福彩可核700次日期與2008029獎訊。 | [500.com固定查詢](https://datachart.500.com/ssq/history/newinc/history.php?start=03001&end=08029)GET200，700列中繼資料可核；官方全期對齊仍缺。 | 官方逐期球組／機號／物理紅球次序**未核實**。API未成功，不聲稱已取得或否定`redSeq`類欄位；紅球升序不得充當次序。 |

缺漏、重複、期號與日期矛盾、矩陣／欄位語義不明均保留原期次並記 **NA／未核實**；不補期、不由前後期插日期、不以備用號碼靜默填官方缺值。來源更正另存原文、URL、擷取時間及雜湊，修正資格狀態但不偷偷替換窗口；未取得所需資料時停止該次，遵守原協議不反覆試閘門。

本輪遇到的實際矛盾也留存：部分2008年歷史報道把700次寫成2月19日，與700列備用期表及江蘇福彩3月13日紀錄不符；不採該報道作邊界。江蘇早期某頁標題、期號與內文亦有不一致，不能因官方網域而直接升格整段資料。上述差異無需任何候選成績即可發現。

## 測試範圍及交付

新測試檢查四組200／500、期號連續與不重疊、日期順序、雙色球年度重設與700列真實中繼資料、預期矩陣與已知排除界線；並用負例確認少一期、重疊、錯矩陣及跨矩陣改制會失敗，未知資格不會被當成可執行。**離線測試不能證明外部來源真偽、未曝光或實體機球制度一致**，也不調用任何出票／回測函式。

窗口初版測試記錄（本輪完整結果見下載審計）：`PYTHONDONTWRITEBYTECODE=1 /tmp/marksix-r2-venv/bin/python -m pytest tests/ docs/review-evidence/test_signal_visibility_diag.py docs/review-evidence/test_external_fair_baselines.py docs/review-evidence/test_external_holdout_windows.py -q -p no:cacheprovider`，結果 **120 passed in 8.21s**。文件與中繼資料／測試的SHA-256納入[校驗清單](review-evidence/SHA256SUMS)，本文件另附同名`.sha256`。保護檔、香港registry及tag不動；attempts仍**14/20，剩6**。
