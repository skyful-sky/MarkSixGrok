# Arian／CPCV核對：不能直接替換本庫逐期向前驗證

核對日期：2026-10-29（HKT）。**CPCV可保留較後期訓練資料來預測較早期測試資料；purging／embargo並不自動保證只用過去。直接套用會違反本庫預測的時間條件，因此本次不移植評估協議。** 本工作不使用六合彩結果訓練或評分，不新增attempt，累計仍14/20、剩6。

## 原文、程式及可重現範圍

核對Hamid Arian、Daniel Norouzi Mobarekeh、Luis Seco，*Backtest overfitting in the machine learning era: A comparison of out-of-sample testing methods in a synthetic controlled environment*，[2024期刊DOI](https://doi.org/10.1016/j.knosys.2024.112477)。

- 出版社及SSRN直接全文／PDF本次受存取限制。已讀取[26頁預印本文字轉載](https://studylib.net/doc/28245570/ssrn-4686376)，其頁內標記為[SSRN 4686376](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4686376)。以作者原文內容作依據，不採網站另加的摘要或問答。**未取得出版社最終PDF，未宣稱與最終版逐頁相同。**
- 相關位置：§1.7（外推限制）、§3.4及§3.4.4（約pp.19–20，CPCV為8組、每次測2組、embargo=0.02）、§3.5（CSCV／PBO／DSR）。原文首頁指向作者組織`github.com/RiskLabAI`的Python程式。
- 核對作者庫[2024-01-26快照](https://github.com/RiskLabAI/RiskLabAI.py/tree/789e71e2c4966e03a581eec95771fe5010dbae1d)及[本次查得的固定快照](https://github.com/RiskLabAI/RiskLabAI.py/tree/7d5aa11271c70d83a7069d5900d80bb08b29e481)，不把浮動main當成2024論文精確執行環境。舊快照也是公開程式歷史，不是已證明與期刊實驗完全一致的release。
- 可重現入口另見作者[模擬notebook固定快照](https://github.com/RiskLabAI/Notebooks.py/blob/c5cef254b83151a9e0378e52b22f2eca52c0a76a/backtest/5_backtest_overfitting_simulation/backtest_overfitting_simulation.ipynb)。本次只執行分割器的合成索引核對，**未重跑論文整套金融模擬、PBO／DSR數值或本庫任何候選**。

原文以合成金融市場及策略的過擬合診斷比較方法，不是六合彩前向成功率證明。其CPCV較佳的結果不能推成所有預測問題都應捨棄只用過去的驗證。§3.4還將多條路徑的同一標籤預測平均；這種離線彙整不會使各路徑的訓練資料回到歷史當時可得的狀態。

## 逐項時間資訊核對

下表把原文設定、程式直接觀察與本庫適用性推論分開。程式來源為固定快照的[CombinatorialPurged](https://github.com/RiskLabAI/RiskLabAI.py/blob/7d5aa11271c70d83a7069d5900d80bb08b29e481/RiskLabAI/backtest/validation/combinatorial_purged.py)、[PurgedKFold](https://github.com/RiskLabAI/RiskLabAI.py/blob/7d5aa11271c70d83a7069d5900d80bb08b29e481/RiskLabAI/backtest/validation/purged_kfold.py)及[模擬流程](https://github.com/RiskLabAI/RiskLabAI.py/blob/7d5aa11271c70d83a7069d5900d80bb08b29e481/RiskLabAI/backtest/backtest_overfitting_simulation.py)。

| 核對項 | 原文／程式所見 | 較後期是否可能進入較早期預測？／本庫判斷 |
| --- | --- | --- |
| 基本分組 | `np.array_split`依次序分組，不隨機打亂；組合選測試組 | **會**：組內保序不代表訓練全部早於測試；其他較後組仍可訓練 |
| 訓練集構造 | `_single_split`枚舉組合，再呼叫`_get_train_indices` | **會**：沒有對每個測試t強制所有訓練標籤可用時間<t |
| Purging | 刪除與test資訊區間重疊的train觀測 | 能處理指定區間的重疊，不會刪除所有較晚且不重疊的觀測；區間定義錯誤也不會被自動修正 |
| Embargo | 在test區間後加有限長排除；現行程式長度為`int(N*embargo)` | 只刪鄰近未來，不刪全部未來；把2%調大也不是本次獲准的修復方案 |
| 模型fit | `X_train/y_train`取purge後索引，fit後再對test預測 | 保留下來的未來標籤確會用於fit；不能僅因test列不在fit內就稱歷史事前預測 |
| 路徑組裝／平均 | 多組模型的test預測依時間拼接；模擬流程對路徑機率平均 | 排序輸出及平均不會消除每個模型fit時已使用的未來資訊，也不增加獨立歷史期數 |
| 標準化 | 所檢視notebook的kNN採`StandardScaler`包在Pipeline，分割器對各train fit | 沒有據此判定它在全資料先fit scaler；但train本身含未來，故仍不符本庫時間條件。移植時任何轉換也須只用合法歷史fit |
| 特徵、暖身與權重 | 模擬流程先建特徵／label／權重，再分割；是否洩漏須逐個函式檢查 | 預先計算本身不必然洩漏，單向歷史rolling可合法；須另查中心化／反向填補、全樣本估計及權重可用時間。不能只靠purging保證整條管線 |
| 額外分支 | 現行特徵函式在`noise_scale>0`時使用全樣本特徵標準差作噪聲尺度 | 該分支可能把較後分佈資訊帶入較早特徵；預設為0、所見主要notebook呼叫未啟用，不冒稱已污染2024全部結果 |
| 選模與指標 | 論文PBO／DSR衡量其金融策略試驗；CSCV再切策略回報矩陣 | 與本庫≥3正選／期、H1條件E值及H3既定門檻不同；重切096–115不能清除已看過資料的選模偏差 |

這裡的「洩漏」是**相對於本庫歷史當時只用已知過去資料預測**的要求。CPCV可用於另外定義的離線跨區間泛化／穩健性問題；不能因此斷言原研究一切結論均無效，但也不能把其holdout預測冒充本庫的即時前向紀錄。

## 純索引重現：purge後仍留下未來

未載入六合彩CSV，也未fit任何模型。建立80個每日時間點，資訊區間起訖相同（點狀標籤），依論文設定`n_splits=8, n_test_groups=2, embargo=.02`。在兩個固定程式快照分別執行其分割邏輯，結果相同：

| 檢查 | 2024快照 | 本次快照 |
| --- | --- | --- |
| 組合分割數 | 28 | 28 |
| 第一分割test索引（0-based） | 0–19 | 0–19 |
| purge／embargo後train索引 | 21–79 | 21–79 |
| 含晚於最早test之train資料的分割 | 27/28 | 27/28 |

例如以21–79期標籤fit後預測索引0，已用到索引0當時未知的結果，雖然train與test點狀資訊區間沒有重疊。這是對時間條件的反例，**不是六合彩候選回測、不是效能排名，也不是對所有區間資料都必為27/28的定理**。

執行只從固定來源擷取原類別AST，略過與分割無關的套件匯入，用空`CrossValidator`基底承接介面；保留實際被呼叫的類別方法／分割及purge內容。NumPy 2.5.4、pandas 3.0.6；沒有安裝RiskLabAI到本庫、沒有改requirements。完整索引與來源SHA見[重現證據](review-evidence/cpcv-index-audit.json)。這種最小執行不等於驗證整個套件或重現期刊全部結果。

可在獨立環境重現同一核對（程式只在記憶體建立合成索引，不讀寫本庫）：

```python
import ast, __future__, urllib.request
from itertools import combinations
import numpy as np
import pandas as pd

for commit in ("789e71e2c4966e03a581eec95771fe5010dbae1d",
               "7d5aa11271c70d83a7069d5900d80bb08b29e481"):
    ns = dict(np=np, pd=pd, combinations=combinations, CrossValidator=object)
    for filename in ("purged_kfold.py", "combinatorial_purged.py"):
        url = (f"https://raw.githubusercontent.com/RiskLabAI/RiskLabAI.py/{commit}/"
               f"RiskLabAI/backtest/validation/{filename}")
        source = urllib.request.urlopen(url, timeout=30).read().decode()
        tree = ast.parse(source)
        tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        exec(compile(tree, filename, "exec",
                     flags=__future__.annotations.compiler_flag), ns)
    index = pd.date_range("2000-01-01", periods=80, freq="D")
    times = pd.Series(index, index=index)
    data = pd.DataFrame({"index_only": range(80)}, index=index)
    cv = ns["CombinatorialPurged"](8, 2, times, embargo=.02)
    splits = list(cv.split(data))
    assert len(splits) == 28
    assert splits[0][1].tolist() == list(range(20))
    assert splits[0][0].tolist() == list(range(21, 80))
    assert sum(any(i > min(test) for i in train)
               for train, test in splits) == 27
```

## 與本庫walk-forward的差異及移植判定

本庫的時間條件是：預測目標t時，只能使用先前期次且在提交／截止前已取得的資料，並先保存該次預測，再揭示t結果。既定程式如[marksix_r2.py](../src/marksix_r2.py)及歷史影子迴圈均要求先預測後更新；整體研究曾看過窗口造成的選模偏差，則是另外一個問題，不能因逐期資料截斷正確便宣稱不存在。

| 比較 | 本庫逐期向前／正式前向 | 所核對的CPCV |
| --- | --- | --- |
| 較早目標的訓練資訊 | 僅先前已可得資料 | 可含較後、但不重疊的train組 |
| 時序狀態 | 依原期序逐期更新，暖身不穿越未來 | 分割及拼接不同模型；須另定義狀態重建，不能直接繼承本庫累積計數 |
| 評估目的 | 當時可實作的逐期預測；H3／H1及META各依既定用途 | 不同holdout安排下的離線表現分佈 |
| 證據資格 | 正式前向須遵守原prereg、提交時間及停止條件 | 多條組合路徑不會產生新的未見開獎資料，不能取代正式前向 |

**本次判定：不可原樣移植為本庫評估協議，不作任何移植。** 若日後另有授權研究，至少須對每個目標檢查所有訓練標籤的可用時間早於該次預測，將資料轉換／選參及狀態更新納入同一限制。加上這種只用過去的限制會改變標準CPCV的分割與路徑數，不能仍直接引用原文的28分割／效能結論。

完整期刊實驗環境及端到端特徵／權重流程尚未復現；目前已足以確認「不重疊」與「只用過去」不是同一要求。無論後續核對是否完成，都不得重切舊窗口來消除既有選擇偏差、改動H3／H1／META用途、復活停用模型或自動登記attempt。原attempts及14/20計數檔保持原樣。
