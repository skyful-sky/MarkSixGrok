# HR-MARKAREA-JOINT-v1：歷史球照與印記面積資料閘門

Manager 2026-10-30 13:46 HKT採納Astra審查後的**資料資格交付**。只查來源、影像可量測性及適用期間，未估計β、未運行模型或八注成功率計算，沒有香港／外部評分。**結論：資料閘門不通過，本案封存；三地合資格實體球組期間均為0，面積數值及β後驗均NA。** 這是資料不足，不能記成回測失敗，也不能推論物理機制已被否定。

依據為[Manager採納的Astra final及原log雜湊](review-evidence/manager-20261030-ev-r3-markarea.json)，原log：`/workspace/research-duo/logs/codex-20261030T053913Z-eefb2a3b.jsonl`。本次沒有建立命中嘗試或修改registry；累計仍14次。

## 1. 閘門及適用範圍

| 必要條件 | 香港 Mark Six | UK Lotto | 日本 Loto6 |
|---|---|---|---|
| 可追溯原始照片／官方圖片來源 | 有2016官方流程照片；不能當成2026同批球 | 有博物館保存的Guinevere展示照片；營辦商歷史球照批次鏈缺 | 有官網機台照片；瑞穗另有插圖，不能量測實物 |
| 全部號碼的可比實物印記影像及校正 | 缺 | 缺 | 缺 |
| 固定面積定義、成像校正及重複量測驗證 | 缺；未確認一致性 | 缺；未確認一致性 | 缺；未確認一致性 |
| 實體球／批次、替換／重印及逐期使用對照 | 缺 | 缺 | 缺；A–J不能代替實體世代 |
| 有效起訖期、當時可取得時間 | 缺／NA | 缺／NA | 缺／NA |
| 決定 | 封存 | 封存 | 封存 |

核對目標為既有香港26/047–115、UK discovery 701–1700、日本結果discovery 701–1146的資料資格，**沒有讀取號碼結果作評分或按結果選球照**。查到更早／更晚的照片也不自動延伸有效期間。UK後來59球照片不能冒作歷史49球實體；日本apparatus補充延伸到2150期也不擴大原結果discovery。未讀`data/external/`封存結果，未新增資料窗口。

以上「缺」是本次有限官方入口、可追溯資產及輔助報導核查的結果，不宣稱全球沒有其他照片或未公開台帳。本輪未向機構索取資料。各請求實際UTC時間、URL、HTTP狀態、原始內容SHA-256及保存方式見[sources.json](review-evidence/hr-markarea-joint-v1/sources.json)；HTTP 403／404與「沒有資料」分開記錄。

## 2. 香港：流程照片存在，欠歷史實體球批對照

- [HKJC 2016-02-19官方流程介紹](https://www.hkjc.com/english/corporate/racing_news_item.asp?in_file=/english/news/2016-02/news_2016021901440.html)連結[原始圖3](https://racing.hkjc.com/image/201602/newsimg_20160219_03.jpg)，取得1655×935 JPEG，可見裝載架及多個印號球，但球面朝向、遮擋、透視、反光不同，沒有全球面尺度校正或逐球實體序號。原圖保存在[影像附件](review-evidence/hr-markarea-joint-v1/images/hk-2016-photo3.jpg)。
- 該2016文章記述抽選球箱、檢查球數及排列，以及量度／稱重／X光程序，**沒有公開逐球量度值、完整印記量測照片、球批壽命或2026逐期球組對照**。文中排列是裝載檢查，不能充當物理出球次序。
- [HKJC 2026-04-21官方公告](https://corporate.hkjc.com/zh-HK/news-and-publications/corporate-news/2026-04/news_2026042101511)說明第四代機器在5月2日攪珠後退役、隨後採第五代；它提供機器更換的制度線索，**沒有證明球組是否同時更換、哪一實體球批用於每一期或印記是否不變**。不能把2016照片沿用到2026，亦不能從機代推定球批世代。
- [官方JC TV入口](https://campaign.hkjc.com/ch/jctv/)不是已取得的逐期、定尺度球面影像庫。本輪未下載影片、擷取幀或量測像素。
- [香港商報2026-06-02參觀報導](https://www.hkcd.com.hk/content_app/2026-06/02/content_8757900.html)為**第三方**。兩張實際取得的1600×1066圖片均主要展示機台，其中可見「TEST DRAWING」標示，沒有可供全部49球一致量測的特寫。其機台／球組敘述不是官方逐期實體台帳；沒有據此確認輪替規則。圖片檔名或報導日期不等於拍攝、首次公開或特定開獎期使用時間。

**適用期間：NA；合資格期數0。** 官方有流程照片，仍欠讓印記面積可比較並可帶入歷史預測的資料鏈。

## 3. 英國：歷史機台展示可追溯，不能認定展示球的服役期

- [National Lottery官方歷史入口](https://www.national-lottery.co.uk/results/lotto/draw-history)本次HTTP 200；入口不是歷史球批的校正照片及換球台帳。其原始回應只留請求雜湊／元資料，未將結果表加入本案資料。
- [Science Museum 2017-05-17文章](https://blog.sciencemuseum.org.uk/international-museum-day/)是藏品機構的一手來源，介紹1994年的Guinevere及2016年10月入展。由頁內`srcset`取得的[768×1024展示照片](https://blog.sciencemuseum.org.uk/wp-content/uploads/sites/12/2017/05/D.R-Image-1-768x1024.jpg)確實可見機器、架上多個球及印記，附件為[原始照片](review-evidence/hr-markarea-joint-v1/images/uk-guinevere-museum.jpg)。但透過展示玻璃、斜視及部分遮擋拍攝，沒有球面尺度／色彩校正；展出一台1994機器不證明架上每球是同年原球，更不能認定其曾用於701–1700任何一期。
- [Science Museum藏品記錄](https://collection.sciencemuseumgroup.org.uk/objects/co8016398/guinevere-random-number-selector-and-name-plaque)直接下載回403；不能當成取得了完整藏品／球批檔案。另取得官方展廳指南PDF，亦未得到逐球實體服役期與印記更換台帳。
- [Gambling Commission「Physical Draw Equipment」](https://www.gamblingcommission.gov.uk/about-us/freedomofinformation/physical-draw-equipment)記請求日2026-08-19、回覆不持有該範圍資料。**範圍限1994年11月至2001年12月**，不能外推為2002–2012或營辦商一概沒有台帳。頁內80g、材質等出現在請求者描述，不能當成監管機構已核實的規格。該回覆沒有提供本案所需的球照、逐球校正或換印記紀錄。
- [lottery.co.uk新機報導](https://www.lottery.co.uk/news/new-ball-machines-for-lotto-draws-and-a-new-studio-in-london)屬第三方，頁示更新2025-07-15；所連900×200圖片實際為攝影機新聞橫額，沒有號碼球，不能當成球照。後期新機報導亦不能補上舊49球的批次使用鏈。

**適用期間：NA；合資格期數0。** Ball Set／Machine欄位即使存在，也不是逐球物理身分、未重印或印記面積不變的證明。

## 4. 日本：官方機台照片與插圖須分開，A–J不代表實體世代

- [宝くじ公式Loto6抽せん方法](https://www.takarakuji-official.jp/kuji/loto/loto6/introduction2.html)有[夢ロトくん照片](https://www.takarakuji-official.jp/assets/img/kuji/pic-yumeloto001.jpg)，實際320×448，可見鼓內部分球；非全部43球的校正特寫，沒有實體セット序號、拍攝日期或歷史使用起訖。附件為[原始圖片](review-evidence/hr-markarea-joint-v1/images/jp-yumeloto-official.jpg)。[官方數字選擇式寶くじ頁](https://www.takarakuji-official.jp/brand/suji/winning-number/)確認機型類別，但未公開該照片對應的球批歷史。
- [瑞穗Loto6產品頁](https://www.mizuhobank.co.jp/takarakuji/products/loto6/index.html)所連[750×444 PNG](https://www.mizuhobank.co.jp/takarakuji/products/loto6/images/loto6_chusen.png)為機台**插圖**，圖像alt亦標イラスト。不能由插圖、向量字型或網頁示範球重建實物印記面積；保存以免日後誤採。
- [既有實體更換史審計](loto6-ballset-lineage.md)的官方世代鏈仍缺，合資格實體校準期數0；A–J的第三方交叉核對只核對字母標籤，並非同一實物批次。今回補查[loto6.info](https://www.loto6.info/?page_id=576)及[hpfreeセット球介紹](https://www.hpfree.com/sml6/miniloto/set.html)等輔助資料，未取得足以取代官方球批／換印記台帳的證據，亦不據第三方世代名稱擴大適用期。

**適用期間：NA；合資格期數0。** 不把相同字母、顏色、字形相似或連續日期當作持續使用同一顆球的證據。

## 5. 面積量度方法：有待驗證的目標，未確認可前後一致

本閘門的物理目標是每顆實球號碼印記（號碼字形及用於識別的底線／點）的**球面面積比例**，即印記面積除以球面總面積；單位為無量綱0–1，底色、陰影、高光、接縫、污損及非號碼商標不算印記。沒有逐期實體對照時，不按號碼字型或號碼結果估值；所有`x_i`為NA。

要確認跨期一致，至少須有：

1. 可識別同一實球／球批的原始多視角影像、球尺寸、相機與鏡頭校正、足夠解析度及受控照明；完整印記區的球面覆蓋。單幅投影像素受姿態及球面縮短影響，不能直接當物理面積。若以其他較少影像的方法代替，仍須有對實物基準的獨立驗證，不能只宣稱字型一樣。
2. 一套固定的去透視／球面重建、分割、陰影與反光處理、識別線條計入規則；盲化重複量測、量測誤差及跨拍攝條件的一致性報告。改尺度、重標準化或換分割器會改變β的意義，須另行審核，不能沿用同一先驗卻悄悄換單位。
3. 該實體球批的製造、替換、補球、重印／重塗與使用起訖，以及逐期使用對照。公開時間／當時可取得時間也須可追溯；後來的照片只能作資料線索，不能倒填為歷史預測時已知量。

上述是資料資格要求，**不是聲稱已經存在或驗證的量測演算法**。目前沒有可填入的校正數、誤差界、實體使用起訖，故不能設定任意誤差門檻後逕行放行。印記面積也不等同墨層厚度、質量、重心或入選機率，照片本身不能證明因果機制。

## 6. 先驗、停止條件及後續界線

依已採納原文，僅保留機制假說`P(D) ∝ exp(β Σ_{i∈D} x_i)`、`|D|=6`及**β先驗`N(0,0.25²)`**。這不是已擬合模型；後驗、參數估計、入選率、八注聯合成功率均NA。若日後資料合格，需先鎖定最終量測定義與單位及完整出票／聯合機率／評估協議，只能用目標期之前可取得資料；不得由正選邊際機率直接代替八注聯合成功率。

本輪三項必要資格——歷史實球照片鏈、一致面積量測、適用期間——均有缺口，按Manager規則**封存HR-MARKAREA-JOINT-v1資料資格案**；不擬合、不實作、不執行命中回測，不把0合資格期誤寫為0命中。補資料後須先重新審核資格及另行授權，不能改閘門反覆試探，更不能自動新增香港attempt；兩國外部門檻通過才可申請香港評估，≥9/20亦僅篩選。未復活停用族，未更動H3／H1／META用途。

本次另將HR-RACK不上線與HR-BOCPD-SUB8擱置記入[A24](lessons.md)。完整來源元資料、未變造影像、原始頁面無損快照與閘門狀態見[附件目錄](review-evidence/hr-markarea-joint-v1/README.md)；SHA-256側檔及總索引供覆核。
