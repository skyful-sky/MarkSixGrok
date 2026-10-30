# cce71b9 步驟二執行收據

Manager已另行授權兩案外部預驗；cce71b9全部方法／參數／指紋保持原樣。
本附件只接線到原數學核，不替換求解器或允許技術失敗重跑。
`src/intradraw_external_validation.py`在執行前核對原實作、規格、來源、
預留槽及環境指紋。新ledger不更動任何既有registry條目。

UK701–900／901–1400，日本701–900／901–1146，分別一次暖身擬合。
200期之後的主號在凍結模型／64模板最大p8收據前不解析。
SHA核對需讀取CSV原始bytes，並非將後期主號交給擬合。
資料及期序缺漏即NA停止，來源未曝光資格仍不合格；這是已曝光探索集
上的預先鎖定篩選，不能稱盲測或確認性通過。

`run/<family>-<country>/`以排他目錄建立阻止第二次執行，run_count=1。
原核每次objective呼叫只加起訖與耗時telemetry，數值傳入／傳出不變。
任何原核失敗均寫terminal結果並封存，命中率／p不可捏造為0；未出票即NA。
各國Random模板固定為第1套，不因模型結果改選。成功擬合並完成模板
核查後，先寫具fsync及SHA的predictions.json，再解析唯一評分窗口。
如模型在出票前失敗，模型及其配對評分均NA，不以Random代替模型。

兩模型各國的獨立確定性運算可並行，均單執行緒，沒有重啟或選最佳。
源資料、香港資料、sealed windows、所有舊結果、tags及既有registry均不寫入。
最後新ledger保留所有四槽的成功／失敗；韓國與雙色球槽仍不使用。
α仍為j2=1/480、j3=1/960，≥2pp及全部共同門檻照舊；香港嘗試仍14。

## Manager重試：bridge中斷後的同次運算續算

上輪四程序已消失，全部停在首輪梯度，沒有接受步、模型、模板或評分。
`recovery-audit.json`保留進入重試時的git狀態與原始start／events雜湊。
已完成objective值依原序重播；逐個以鎖定初始化及中央差分位置核對
U／probe旗標，完全一致才可採用。未完成的objective接續原核計算。
這是恢復同一次尚未完成的首輪梯度，不重抽起點、不丟棄失敗結果，
run_count仍1。完成過接受步、模型、預測、結果或數值停止者均禁止此恢復。
原始events不覆寫，續算另寫resume-events；再中斷不自動重新啟動。

原核一輪梯度實測約需19–74分鐘，完整擬合可能遠超bridge回覆時限。
`supervise.py`以獨立程序持續此同次運算，四槽各只續算一次；不收斂
照原門檻封存。全數terminal後才由finalize整理台帳，另列固定Random
的描述性結果（即使模型未能出票，該模型命中／配對仍NA）。
隨後跑完整隔離測試、核對保護項、commit並只push origin main。
任何意外程序退出、測試失敗、保護項變動或push拒絕均停下留錯誤紀錄，
不重跑擬合、不強推、不改tag。狀態記於/tmp/marksix-intradraw-supervisor.log；
完成收據為/tmp/marksix-intradraw-completion.json，兩者不屬已封存結果。
