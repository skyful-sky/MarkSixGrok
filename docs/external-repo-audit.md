# 外部GitHub項目靜態審查

審查日期：2026-10-29（HKT）。目標庫基準：`f30d08ea2fc38f6cc26e35b3b3c6403e52bdbf88`。本工作只讀取外部原始檔及資料欄位，不匯入或執行外部程式、不載入模型權重、不回測26/096–115；不新增shadow ID或attempt，仍14/20、剩6。缺項一律以「缺」標記，不以程式功能或檔案日期代替已發生的事前預測證據。

## 釘選版本

GitHub連線以各庫預設分支HEAD解析出下列完整commit SHA；其後讀取均指定該SHA，不使用浮動main/master作審查依據。commit日期是版本中記載的日期，不是開獎前公佈預測的證據。

| 項目／來源URL | 釘選SHA | commit記載日期（UTC） |
| --- | --- | --- |
| [jeremychan/serverless-mark-six-result-scraper](https://github.com/jeremychan/serverless-mark-six-result-scraper/tree/5bf88901758ef4a0c1717316f1ba862da5f0edd7) | `5bf88901758ef4a0c1717316f1ba862da5f0edd7` | 2019-06-16T22:57:18Z |
| [8280998/MarkSix](https://github.com/8280998/MarkSix/tree/5f1e909ae09fee49810ea11882cd03c83a502fdd) | `5f1e909ae09fee49810ea11882cd03c83a502fdd` | 2026-04-07T16:01:41Z |
| [TedLLH/HongKongPowerBall_MarkSix](https://github.com/TedLLH/HongKongPowerBall_MarkSix/tree/1538bfe23a81af13baaebb467f08892ee10cd228) | `1538bfe23a81af13baaebb467f08892ee10cd228` | 2025-03-17T00:06:28Z |

## 1. jeremychan：結果抓取器，來源實為第三方

證據：[handler.js](https://github.com/jeremychan/serverless-mark-six-result-scraper/blob/5bf88901758ef4a0c1717316f1ba862da5f0edd7/handler.js)、[helpers.js](https://github.com/jeremychan/serverless-mark-six-result-scraper/blob/5bf88901758ef4a0c1717316f1ba862da5f0edd7/helpers.js)、[serverless.yml](https://github.com/jeremychan/serverless-mark-six-result-scraper/blob/5bf88901758ef4a0c1717316f1ba862da5f0edd7/serverless.yml)。

| 核對項 | 靜態所見／缺項 |
| --- | --- |
| 資料來源URL | 程式實際請求 `http://lottery.hk/liuhecai/jieguo/{YYYY-MM-DD}`，不是直接請求馬會官方網域；本次未執行請求 |
| 欄位語義 | 從頁面 `.result .balls li` 的文字依DOM次序收集，再把最後一項當 `specialNumber`、前面當 `numbers`；儲存 `drawDate/numbers/specialNumber/createdAt` |
| 官方出球次序 | **缺**。DOM位置不是官方逐球次序證明，程式沒有取得可驗證物理次序的官方紀錄 |
| 資料可用時間 | 抓取函式查當日及前6日；`createdAt` 是本次入庫的本機時間。實際來源發佈時間、各期首次可得時間、來源不可變存檔：**缺**。GET結果投影更只回傳日期、主號、特別號 |
| 預測先於結果的證據 | **缺**。可見程式提供結果抓取／查詢，不提供已提交的事前預測紀錄 |
| 檢定次數 | **缺**；沒有可核驗累計試驗紀錄，不把未見檢定程式推成「0次」 |
| 選模次數 | **缺**；沒有可核驗模型搜尋／選擇紀錄 |

已查非套件原始碼及部署設定；未部署、未呼叫scrape端點，未讀取第三方網站現時結果。

## 2. 8280998：有預測／復盤流程，未取得不可改寫的事前證據

證據：[marksix_local.py](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/marksix_local.py)、[CSV](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/Mark_Six.csv)、[官方源讀入器](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/web/src/lib/official-source.ts)、[prediction-service.ts](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/web/src/lib/prediction-service.ts)、[schema.prisma](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/web/prisma/schema.prisma)、[Web策略](https://github.com/8280998/MarkSix/blob/5f1e909ae09fee49810ea11882cd03c83a502fdd/web/src/lib/strategies.ts)。

| 核對項 | 靜態所見／缺項 |
| --- | --- |
| 資料來源URL | 預設 `https://bet.hkjc.com/contentserver/jcbw/cmc/last30draw.json`；另有可設定第三方URL及Lottolyzer回退。實際每次執行採用的來源及當時原始回應：**缺** |
| 欄位語義 | CSV有期數、日期、六正選、特別號及衍生統計／派彩欄。所讀樣本六正選升序；讀入器將 `n1..n6` 或號碼串前六項作 `numbers`，並另抽特別號。欄名位置不代表物理次序 |
| 官方出球次序 | **缺**。未見經官方語意核驗的逐球欄位、影片轉錄或來源鏈；設有官方源URL不等於取得官方次序 |
| 資料可用時間 | DB有日期、來源標籤及createdAt／updatedAt；日期解析可填入固定中午時刻。各期官方首次發佈時間、資料於每次預測前已可得的證據：**缺**；固定解析時刻不是開獎／發佈時間 |
| 預測先於結果的證據 | **缺**。有PENDING→REVIEWED及createdAt欄位，但Python及Web可覆寫同一期預測與時間；Web生成函式未依傳入目標期截斷draws。公開且不可回改的預測內容、提交時間與官方結果時間對照：**缺** |
| 檢定次數 | **缺**。未取得完整累計檢定／重跑紀錄及多重比較族 |
| 選模次數 | 實際累計次數：**缺**。可靜態確認Python定義6策略、Web定義4策略；Python挖掘格為5個窗口×9組權重×4組pair/zone＝180候選設定。這些是程式設計數量，不是已執行或獨立選模次數 |

具體位置：Python約839–955行列出候選格並取歷史評分最佳設定；1076–1120行生成／覆寫預測；1141–1208行歷史回放使用target之前資料，pattern分支每50期重新挖掘。這段截斷是可見設計，不能代替實際事前公佈證據或完整選模帳。Web復盤針對特別號的指標，與本庫「八注至少一注≥3正選」也不是同一統計量；未執行或移植任何一段。

## 3. TedLLH：排序欄位與探索／訓練分支，缺官方次序及前向證據

證據：[README](https://github.com/TedLLH/HongKongPowerBall_MarkSix/blob/1538bfe23a81af13baaebb467f08892ee10cd228/README.md)、[Mark_Six.csv](https://github.com/TedLLH/HongKongPowerBall_MarkSix/blob/1538bfe23a81af13baaebb467f08892ee10cd228/Mark_Six.csv)、[marksix.ipynb](https://github.com/TedLLH/HongKongPowerBall_MarkSix/blob/1538bfe23a81af13baaebb467f08892ee10cd228/marksix.ipynb)。Notebook blob SHA為 `6c2dc49ba92b5be93ce43185a19a32f4efd6a580`；透過blob讀取並解析JSON文字，沒有執行cell。模型權重及已提交的虛擬環境均未載入。

| 核對項 | 靜態所見／缺項 |
| --- | --- |
| 資料來源URL | Notebook讀取本庫CSV及部分Kaggle檔案路徑；對應開獎原始資料的可追溯官方來源URL：**缺**。GitHub檔案URL不等於原始開獎資料來源 |
| 欄位語義 | CSV有Draw、Date、六Winning Number欄、Extra Number及統計／派彩欄；所讀樣本六主號升序。Notebook cell index 11把六主號改名為 `1st…6th`，是程式重新命名 |
| 官方出球次序 | **缺**。`1st…6th` 或位置特徵不是官方出球順序證明，未取得官方次序表或影片來源鏈 |
| 資料可用時間 | CSV日期是結果日期；Notebook另有由結果衍生的累積／rolling特徵及真實與合成資料串接。各特徵於預測前的實際可用時間／來源發佈時間：**缺** |
| 預測先於結果的證據 | **缺**。Notebook執行序號、訓練檔名／log時間不是截止售票前的獨立預測提交證據；未取得可核驗的逐期前向預測帳 |
| 檢定次數 | 實際累計次數：**缺**。可見多個Shapiro-Wilk、逐值t-test及探索分支；cell重跑與完整多重比較族：**缺** |
| 選模次數 | 實際累計次數：**缺**。可見不同資料規模／分類器／深度模型／評估閾值等分支，沒有完整選模／重調帳 |

Notebook共有504個cell，其中338個code cell。以上cell index採0-based：53／70含Shapiro-Wilk，55／72含逐值t-test；389／484呼叫train_test_split，未列shuffle=False或只用過去的日期條件；416串接真實與合成資料；488含訓練集scaler及分類器分支，492為另一訓練／驗證分支。僅憑這些靜態內容，嚴格逐期向前驗證證據仍為「缺」，不將Notebook內指標當作本庫可用訊號。未計算其命中率，未重跑檢定、訓練、特徵或模型評估。

## 總結及驗證狀態

三項均未取得可核驗的官方逐球出球次序；目前原始有序／鼓偏似然所缺資料仍未補足。每項完整檢定與選模實際累計次數皆「缺」；不把可見程式分支數當成真實嘗試總數，也不把未找到紀錄當作機制已被否定。

上一輪在唯讀沙箱執行測試，預設輸出捕獲無法建立暫存檔；改以sys捕獲後取得84 passed、12項因tmp_path設定無可寫暫存目錄而出錯。該結果是上輪限制，不能當作本輪測試結果。

本輪環境已可寫，未改程式或測試，執行全套既有測試與合成診斷測試：

```text
PYTHONDONTWRITEBYTECODE=1 /tmp/marksix-r2-venv/bin/python -m pytest tests/ docs/review-evidence/test_signal_visibility_diag.py -q -p no:cacheprovider
96 passed in 5.34s
```

本次只將已完成的靜態審查落盤；沒有執行任何外部模型或26/096–115回測。交付為本文件與旁附SHA-256校驗檔。所有既有資料、協議、H3／H1、META-BORDA及26/116預測保持原樣；attempts及其registry不改，仍14/20、剩6。本輪文件及外部來源SHA是追溯資訊，不是新的預測方法或事前有效性證明。

## 與上一輪草稿的差異

上一輪草稿SHA-256為`ee8809090da3340840b40f84075f957cfb6e771e4f91db97c0384c6fea9a3206`，從log `codex-20261029T043535Z-f409d36e`還原並核對完全一致。三項目釘選SHA、來源URL、欄位語義、資料可用時間、事前預測證據、檢定／選模次數及審查結論均不變；僅更新「總結及驗證狀態」中的執行／交付說明，並新增本差異紀錄：保留上輪84 passed／12項設定錯誤作歷史，新增本輪96 passed，並將未落盤／無法提交的狀態改為本輪文件及校驗檔交付說明。沒有另選外部版本、補造缺項或改動方法。
