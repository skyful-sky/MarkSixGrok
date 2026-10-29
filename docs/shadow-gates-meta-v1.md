# 暖身閘門與 META-BORDA 影子前向

Manager 授權本次A13審核、DISPREG／COMPREV條件候選，以及直接前向的META-BORDA。原始Research為`agy-20261029T015125Z-15a52017.stdout.json`及`agy-20261029T020332Z-70c4485f.stdout.json`。參數、實作、來源與依賴SHA-256先記入registry／鎖定檔並commit，再計算閘門及新預測。正式CSV、prereg-r2/H3及原26/116預測不修改。

## 前置閘門（不占歷史窗模型額度）

僅用26/047–066的20期／19個相鄰對。Pearson分別對左、右19值扣各自均值；若任一lag向量為常數，r記0，不能通過方向條件。置換以NumPy `default_rng(20261029)`生成10,000個完整20期次序，兩個閘門共用同一批次序；O/H始終整期成對打亂。p包含等值，採plus-one除10001，門檻均是嚴格不等式。

- **DISPREG**：D為六正選樣本標準差（ddof=1）。需`r_D>0`且上尾置換p<0.20。
- **COMPREV**：O為單數數目，H為25–49數目。需`r_O<0`且`r_H<0`，並對`S=r_O+r_H`取下尾置換p<0.20。

registry的`GATE-SH-*`記錄只登記待檢前置；失敗即撤回、不執行該模型歷史回測／MC、不新增`SH-*`歷史嘗試。通過後才新增canonical模型ID並commit，之後才跑該版完整回測。

## 通過時才可執行的候選

- **SH-DISPREG-v1**：半衰期3正規化EWM of D，與全部先前D的中位數比較；嚴格較低為聚集，否則分散。聚集八注固定1–6…43–48；分散八注為`{k,k+8,…,k+40}`，k=1…8。兩者均剔49。這是注型模型，**沒有平均排名**，以`M_t=八注最大正選命中數`及其平均M̄報告，並報命中及MC p。另報分散期中的FixedBlocks／DISPREG命中；主窗或全49期聚集比例>50%時只描述。
- **SH-COMPREV-v1**：四格細單／細雙／大單／大雙，大小12／12／13／12；`e_c=6*size/49`、`pred_c=e_c-0.5*(上期count-e_c)`、`score=pred_c/size`。不裁去負預測值。精確有理數整數鍵排序，同分使用獨立`random.Random(20261029)`，每個可計分期洗牌1–49一次，暖身不消耗亂數。排名1–48切八注，主要平均排名用同分平均排名，另存實際切注序位；同時報命中及M̄。

通過者才以相同觀察／MC引擎評估067–095、096–115及全49期。MC為10,000條完整69期公平六子集歷史，重做暖身及更新；單尾p為命中／M總和上尾、COMPREV midrank總和下尾，皆plus-one。這些是固定模型的描述性虛無校準，不聲稱消除前置選擇或已見資料偏差。本次不把Research建議的「兩段排名p<0.10亦可通過」偷偷套入舊版規則，也不自動授權任何前向確認；<9/20仍停用。

## META-BORDA：不做096–115篩選

見[prereg-r3](../prereg/round3.yaml)，自26/116另存影子紀錄。十個組件固定等權：GAP1、GAP20、LAG1、RNO、HARM48、WDAY20、RESFOLD、CENTROID、TAIL、ORDSTAT，無論既往成績一律保留，不能挑模型／權重。不納入BLOCKX或DISPREG，不消耗同窗attempts。

聚合名次統一指每個組件既定出票的實際序位1–49；HARM／WDAY過去用midrank報告是另一個統計口徑，不混進Borda輸入。各組件原分數、參數、同分規則不變，HARM／WDAY沿來源先四捨五入12位、同分小號優先。種子組件沿用從067開始的既定亂數流；程式只跳過已過期次所需的洗牌次數，不重跑已停用模型的歷史回測。

每碼十個名次求和（等價於平均），越低越前；Borda同分以獨立`random.Random(20261029)`，前向期序自116開始。前48每六碼一切，其餘剔除。初期WDAY日期固定為既有官方公告的2026-10-31，來源在prereg-r3保存；不用未來開獎結果決定日期。

本次prereg-r3是**紙上影子記錄協議**：不分配確認性α、不自行借用H1的E值門檻、不宣告通過，也不占H3正式八注；若要確認性推論，須在相應未見資料之前另立完整測試協議。組件原停用紀錄保持原狀；納入等權影子不是恢復原模型篩選或調參。

```bash
/tmp/marksix-r2-venv/bin/python src/marksix_shadow_gates.py gates
# 只有通過閘門並新增正式模型registry記錄及commit後，才可執行：
/tmp/marksix-r2-venv/bin/python src/marksix_shadow_gates.py backtest
/tmp/marksix-r2-venv/bin/python src/marksix_meta_borda.py
```

所有輸出拒絕覆寫；META僅提供前向預測命令，沒有歷史篩選入口。原正式預測保持在原檔；新影子另放`forward/meta-borda/`，含UTC／HKT、資料／協議／程式及payload SHA-256，另有檔案checksum。

## 首次META存檔前的實作修正

首次前向預測計算後，序列化呼叫因漏匯入canonical_json而以NameError停止，未寫入任何預測檔。以另行commit修正匯入並補CLI存檔／校驗碼／拒絕覆寫測試；prereg-r3、公式、組件權重、種子與閘門結果均不變。META實作鎖定檔保存舊新程式與鎖定檔SHA-256的更正鏈。這不是歷史篩選或新模型版本，不占attempts。

## 暖身閘門實際結果：兩版均撤回

| 候選 | Pearson觀測值 | 單尾置換p | 處置 |
| --- | --- | --- | --- |
| SH-DISPREG-v1 | r_D=0.0027659023 | 上尾0.3935606439 | p未達標，撤回 |
| SH-COMPREV-v1 | r_O=0.0054360673、r_H=−0.0929203540；S=−0.0874842867 | 下尾0.5176482352 | r_O非負且p未達標，撤回 |

只使用047–066的20期／19對；各以同一批10,000個完整期次置換計算plus-one p。見[完整閘門紀錄](../backtests/shadow-gates-v1.json)。兩個候選的067–095、096–115命中／排名／M̄及後續MC均為**不適用（未執行）**，不是0/20。不增加canonical模型attempt；總計仍13/20，剩7。META是另外授權的前向影子，不以閘門結果調權或篩選。
