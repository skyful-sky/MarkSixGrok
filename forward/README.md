# Round 2 前瞻紀錄

本輪固定由 **26/116** 起連續 60 期，正式投注為 H3 的 1–6、7–12、…、43–48 八注，每期 $80；49 不入注。成功指至少一注含 ≥3 正選，每期最多記一次，特別號不計。H1 只作影子報告，不能更改正式八注。完整設定見 `prereg/round2.yaml`，程式版本由 annotated tag `prereg-r2` 指向的 commit 鎖定。

目前僅本機鎖定，尚未核實公開預註冊。本次作業禁止 push；本機 commit/tag 不代表已於截止前公開。Manager 必須核實 26/116 的馬會官方開獎時間、截止售票時間，以及公開倉庫上 tag 的時間和網址，另行 commit 證據。在證據未核實前，評估預設為 `publication_unverified`，不可宣告通過。

若未在首期截止售票前公開，或發生攪珠機／球組更換、取消或延期，原輪作廢／中止，不得順延、補期或延長。保留 `prereg-r2`，另行 commit 註明原因；重新計算資料雜湊、指定新首期並另開 `prereg-r2b`，不可覆寫舊 tag。

## 執行與重現

```bash
python3 -m venv /tmp/marksix-r2-venv
/tmp/marksix-r2-venv/bin/python -m pip install -r requirements.txt
/tmp/marksix-r2-venv/bin/python -m pytest tests/ -q
sha256sum marksix_data.csv
/tmp/marksix-r2-venv/bin/python src/marksix_r2.py predict
```

鎖定快照為 `marksix_data.csv`（26/047–26/115，69 期），SHA-256 必須為 `653993bd43030f7436a96a171ba98b2e73ed62e26f38108efd334fe3d88c8a5e`。保留原始 BOM／CRLF 位元組，勿把新期數附加到這個快照。新結果另放 `forward/results.csv`，使用相同中文表頭和欄位順序：

```csv
期數,攪珠日期,正選號碼1,正選號碼2,正選號碼3,正選號碼4,正選號碼5,正選號碼6,特別號碼
```

Manager 以香港賽馬會官方結果為準逐期追加；不在程式內抓取未核實來源。首筆一定是 26/116，不能跳期，跨年從新年份 /001 接續；60 期終點按實際連續期次計，不能假定全在 2026 年。

每期截止售票前，以 UTC 時間命名保存預測（例如 `forward/26-116.prediction.20261028T150000Z.json`），記錄擷取時間、官方截止時間及來源，然後逐期 commit。首期 `predict` 使用預設目標；後續範例如下，`results.csv` 必須只包含已開獎期：

```bash
/tmp/marksix-r2-venv/bin/python src/marksix_r2.py predict --future forward/results.csv --target 26/117
/tmp/marksix-r2-venv/bin/python src/marksix_r2.py evaluate --future forward/results.csv
```

stdout 是穩定排序的 JSON；相同輸入兩次的 SHA-256 必須一致。實際存檔時間獨立記在檔名及審核紀錄，不能以重建輸出的時間冒充事前提交時間。保存預測 JSON、結果、資料來源、UTC 時戳和 git commit；開獎後保存 evaluate 的輸出。漏交仍使用鎖定程式重建並照算，例如 `evaluate --future forward/results.csv --late 26/116`，不可刪除輸期或只報成功。更正另行 commit，註明來源與原因，不改寫歷史。

只有 Manager 已保存「公開 tag 早於官方截止售票」的可核對證據，才可使用 `evaluate --public-before-cutoff-verified`；這是人工證據核實聲明，程式不會代查 GitHub／馬會或證明其真偽。發生作廢事件時使用 `--invalidate machine_change` 等原因，並補記 registry。CLI 不會因本機 tag 存在而自動開啟有效性。

## 固定判定

- H1：只用目標期之前、自 26/047 起的正選；上一期 age=1，權重 `2^(-age/20)`。分數由高到低，同分平均排名；影子切注同分按號碼升序。`A_t=25-正選平均排名`，λ=0.1，每期以該期實際平均排名向量的 e₆ 計算條件分母。log_E 穩定累加。唯一通過條件是第 60 期 `E_60>=60`，ΣA 只是附報。
- H3：公平成功率 `12344/83237`；唯一通過條件是第 60 期成功 ≥16 次。15 次不通過。
- 第 20／40 期若 H3 **累計**成功 ≤2／≤5，且**截至該期的累計**正選平均排名 ≥25，立即無效停止整輪；兩假說皆不得通過。即使早期 E 已超過 60，仍不得提前通過。
- 每 20 期報最近 20 期正式及影子成功率。停止後不再納入後續期數；若提供超過 60 期資料，程式拒絕延長窗口。
- 第 60 期未達門檻就停用該版本。H1 失敗須註明：「方法保守，未通過本身不足以排除中等效應」，仍不能宣稱有訊號或改用 ΣA 判定。
- H1、H3 各配置 1/60 錯誤額度，餘下 1/60 預留 H2。任一通過後才可用新資料另行預註冊 H2；H1 通過並不證明八注有效。新版本不能反覆沿用舊額度。

目前沒有已確認預測證據。固定區塊 8/20、24 碼 2/20、置換 p≈0.00697 全是探索，已補記 `registry/attempts.csv`，不得納入本輪。Antigravity 對 H1 的完整保留異議亦保存在 registry，功效數字僅為近似估算。
