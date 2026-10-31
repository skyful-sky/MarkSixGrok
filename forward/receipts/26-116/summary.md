# 26/116 前向評分收據

期數26/116，2026-10-31；正選 **10、11、19、27、37、43**；特別號 **8**（全部排除於主號命中計算）。Tim確認未買實體票，本次全屬紙面追蹤。

來源：[lottery.hk 日期專頁](https://lottery.hk/en/mark-six/results/2026-10-31)，已實際抓取並與Manager提供數字核對一致；它是次級轉錄來源，並非HKJC官方網域。[HKJC官方入口](https://bet.hkjc.com/ch/marksix/results)只取得SPA殼，沒有直接核實官方結果JSON。兩次抓取時間、HTTP狀態、原始HTML內容SHA及gzip檔SHA見source-receipt.json。

| 套別 | 第1至8注正碼命中數 | ≥3正碼成功 | 最佳注及實際命中正碼 |
|---|---|---|---|
|H3|0,2,0,1,1,0,1,1|否|第2注 7,8,9,10,11,12；中10,11（2碼）|
|H1影子票|0,0,0,1,1,3,1,0|是|第6注 16,43,23,32,10,27；中10,27,43（3碼）|
|META-BORDA影子|0,3,0,1,0,0,1,1|是|第2注 19,20,11,5,41,27；中11,19,27（3碼）|
|HK-MACH-ALT-v2|0,0,2,1,1,2,0,0|否|第3注 8,19,25,31,37,41中19,37；第6注15,16,18,27,43,44中27,43（並列2碼）|

H1主指標與影子票須分開：正選平均排名31.6666666667，A=-6.6666666667，log E₁=-0.8152218625515538，**E₁=0.44254113316397503**。影子票中三碼不能替代第60期E₆₀≥60的主關口。

H3目前累計 **0/1**，即固定60期窗口的第 **1/60** 期；最終須≥16/60。20／40期無效停止檢查尚未到期，本期futility_triggered=false。
HK-MACH正式u=1，**k/n=0/1**，固定≥43/200有效攪珠關口仍pending，statistical_threshold_met=false、passed=false，未延長、重設或改參。
META正選平均實際切注排名22.1666666667；正選的平均Borda成分名次分數24.0166666667，只附報；alpha=null，沒有通過關口或推論聲稱。

四套沒有觸發任何預註冊通過或停止閘門。publication_unverified保持不變；倉庫本輪讀取仍為PRIVATE，沒有新增獨立公開時間證據，未傳--public-before-cutoff-verified。既有凍結檔存在且逐欄匹配鎖定重建，沒有已知缺交，故未傳--late；此舉不代表已核實公開事前提交。

對獎資料寫入forward/results.csv；R2 CLI原樣stdout見r2-evaluate.stdout.json；META與HK另存26-116.score.json。HK ledger只追加一行，舊註冊行位元組保留，其前綴長度／舊SHA與追加後SHA在scores.json。舊prereg證據SHA256SUMS保留為當時歷史快照；本次追加後ledger以本收據的新SHA256SUMS核對，沒有改寫舊校驗證據。

驗證：獨立集合交集核對全部32注，另以完整六碼子集合的整數排名和分布重算H1條件分母及E₁，均吻合鎖定CLI。特別8若誤計主碼會把H3與HK錯算為成功，已明確防止。

相關測試：56 passed in 3.83s；tests/test_r2.py、tests/test_shadow_gates_meta.py、tests/test_hk_mach_alt_v2.py及tests/test_hk_mach_alt_v2_artifacts.py；沒有運行INTRADRAW測試／擬合／評分，也未中斷其supervisor。
沒有新增預測、ID、命中嘗試或alpha；累計嘗試仍15。凍結票、CSV快照、prereg、H3邏輯、tags、registry及既有封存結果保持不變。
