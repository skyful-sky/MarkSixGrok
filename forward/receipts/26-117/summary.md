# 26/117 前向評分及入帳收據

26/117，2026-11-05；正選 **11、20、28、29、42、47**；特別號 **46**，不計正碼命中。紙面追蹤，沒有實際購票。

已實際抓取[lottery.hk 日期專頁](https://lottery.hk/en/mark-six/results/2026-11-05)，日期、期號、正選及特別號與Manager提供資料一致。它是次級結果轉錄來源，不是HKJC官方網域。[HKJC官方入口](https://bet.hkjc.com/ch/marksix/results)只取得SPA殼，未直接取得官方結果JSON。各來源URL、擷取UTC、HTML內容SHA及gzip快照SHA見source-receipt.json。

| 套別 | 第1至8注正碼命中數 | 最佳注（完整票） | 實際命中正碼 |
|---|---|---|---|
|H3|0,1,0,1,2,0,1,1|第5注 25,26,27,28,29,30|28,29（2碼）|
|H1影子票|1,2,0,1,0,0,1,1|第2注 5,47,11,8,18,2|11,47（2碼）|
|META-BORDA影子|1,0,0,1,1,1,0,2|第8注 42,11,49,37,10,46|11,42（2碼）|
|HK-MACH-ALT-v2|1,0,1,0,0,2,1,1|第6注 15,20,28,30,38,44|20,28（2碼）|

四套本期均未達「至少一注≥3正碼」，一期最多記一次。META最佳注雖另含特別46，仍只有2正碼，不能算成功。

H1本期正選平均排名 **21.3333333333**，A=**3.6666666667**；log E本期增量0.21811147078177984，累計log E₂=−0.597110391769774、**E₂=0.5503997801665572**。H1影子票累計1/2只附報，不能取代第60期E₆₀≥60的唯一主關口。

H3累計 **0/2**，即60期窗口已完成 **2/60**；最終門檻≥16/60，20／40期無效停止檢查尚未到期。HK-MACH本期u=2、hit=0，**running k/n=0/2**；首200次有效攪珠須≥43，仍pending，沒有提前通過。

META本期正選平均實際切注排名29；影子成功累計1/2，alpha=null、pass_claim=null，不作推論或通過聲稱。

沒有觸發任何預註冊通過／停止閘門；futility_triggered=false。publication_unverified保持不變，沒有使用--public-before-cutoff-verified。凍結票存在、SHA及各欄內容匹配鎖定程式，時間戳早於已存日程截止；無已知缺交，未加--late。這不等於已證實截止前公開提交。

forward/results.csv僅追加117，原表頭及116行位元組保留；R2原樣evaluate stdout另存。META及HK分別新增26-117.score.json，HK ledger只加一行score事件；兩者舊前綴長度、SHA與追加後SHA留帳。舊各期SHA256SUMS保留當時ledger／CSV歷史狀態，本收據SHA256SUMS核對本次追加後狀態。

驗證：獨立核對全部32注主號交集，並以兩期完整六碼子集合的整數排名和分布獨立重算H1條件分母、增量及累計E₂，與鎖定CLI一致；兩期凍結H3/H1 payload均逐欄核對。
相關測試：**56 passed in 3.80s**；test_r2、test_shadow_gates_meta、test_hk_mach_alt_v2及其artifact測試。沒有執行INTRADRAW測試／擬合／評分、沒有中斷supervisor，也未納入其未追蹤run檔。

沒有改動凍結票、prereg、H3程式、marksix_data.csv、registry、tags或舊收據；沒有新增預測、ID、alpha或嘗試，香港累計命中嘗試仍15。
