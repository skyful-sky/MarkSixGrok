# 前向紀錄核對：prereg-r2 與 META-BORDA

核對基準：`940823bcd0ac74bf55e58ec9de0fb5d3ed366394`（GitHub `main` 同步確認）；查核時間為 2026-10-29 04:56 UTC／12:56 HKT。本次只讀取既有紀錄、重算檔案及 payload 雜湊、核對 Git／GitHub 中繼資料及官方網頁。沒有執行新預測或歷史回測，沒有新模型 ID 或 attempt。

## 逐期清單

此基準的 `forward/` 只有兩個預測 JSON；兩者目標都是 **26/116**。prereg-r2 的同一檔案含 H3 正式八注與 H1 影子八注，並非兩次獨立提交。META-BORDA 是 prereg-r3 的獨立影子紀錄。沒有其他已存前向期次；60 期規劃不等於已有 60 期提交。

| 協議／紀錄 | 目標期 | 歷史資料截止 | 預測檔案 | 官方結果 URL／本庫結果檔 | 命中情況 |
|---|---|---|---|---|---|
| prereg-r2：H3 正式 | 26/116 | 26/115，2026-10-27 | [R2 JSON](../forward/26-116.prediction.20261029T001900Z.json) | 該期已發布官方結果 URL：缺；本庫結果檔：缺 | 缺；未取得該期結果，不填 0 次或失敗 |
| prereg-r2：H1 影子 | 26/116 | 26/115，2026-10-27 | 同一 R2 JSON，`H1_shadow`、`scores`、`ranks` | 同上：缺 | 缺；A、log_E、累計 E 及影子命中均未評分 |
| prereg-r3：SH-META-BORDA-v1 | 26/116 | 26/115，2026-10-27 | [META JSON](../forward/meta-borda/26-116.prediction.20261029T022640Z.json) | 同上：缺 | 缺；未評分；用途仍僅前向影子紀錄 |

兩檔均指向 `marksix_data.csv` 的 69 期快照，自 26/047 起、只用正選，訓練資料 SHA-256 為 `653993bd43030f7436a96a171ba98b2e73ed62e26f38108efd334fe3d88c8a5e`。本次確認快照內容及雜湊，沒有重新取得或逐列重驗上游歷史資料。

官方結果查閱入口：[香港賽馬會六合彩結果](https://bet.hkjc.com/ch/marksix/results)。本次網頁讀取只取得「You need to enable JavaScript to run this app.」，沒有取得 26/116 的正選、特別號或該期官方結果文件。`forward/results.csv` 亦不存在。入口 URL 不等於已取得該期結果來源，故上表仍填「缺」。

## 時間證據與公開狀態

下列 UTC 與 HKT 換算一致；`recorded_at` 是原檔自載時間，Git author／committer 時間是提交者寫入的中繼資料。兩類都不是獨立可信時間戳。GitHub REST 本次回傳的 commit 日期與本地一致，但這些日期不是 GitHub 首次接收或向公眾發布的時間；兩個預測提交均為 `unsigned`，`verified_at` 為 null。

| 紀錄 | 原檔記錄時間 UTC／HKT | 首次加入檔案的 commit | author 與 committer 時間 UTC／HKT | 首次 push 的伺服器接收時間 | 可核證公開時間 |
|---|---|---|---|---|---|
| R2（H3＋H1） | `2026-10-29T00:19:00.850104Z`／`2026-10-29T08:19:00.850104+08:00` | [b27e50a23f29eae542514afc437ca0d58142e192](https://github.com/skyful-sky/MarkSixGrok/commit/b27e50a23f29eae542514afc437ca0d58142e192) | `2026-10-29T00:19:27Z`／`2026-10-29T08:19:27+08:00` | 缺 | 缺 |
| META-BORDA | `2026-10-29T02:26:40.741754+00:00`／`2026-10-29T10:26:40.741754+08:00` | [3e8081624fee35edb683373f7603ac895a82bb27](https://github.com/skyful-sky/MarkSixGrok/commit/3e8081624fee35edb683373f7603ac895a82bb27) | `2026-10-29T02:30:48Z`／`2026-10-29T10:30:48+08:00` | 缺 | 缺 |

其他可核對紀錄及其限制：

- R2 的 `generated_at_utc` 為 `2026-10-29T00:19:00.418950Z`；官方來源查閱自載時間為 `2026-10-29T00:19:00.850104Z`。這些仍屬檔內聲明，沒有獨立時間戳憑證。
- R2 鎖定 commit：[a68279de5c8f676829a7edeb3d44abfd595ad82f](https://github.com/skyful-sky/MarkSixGrok/commit/a68279de5c8f676829a7edeb3d44abfd595ad82f)，author／committer 均為 `2026-10-28T22:20:54+08:00`（UTC `2026-10-28T14:20:54Z`）。annotated tag `prereg-r2` 的 tagger 時間相同；tag object 為 `3f39e09868d105b68805b2b5c0aa32af2b9c4da5`。tagger 時間並不證明公開時間。
- R3 的 `locked_at_utc` 為 `2026-10-29T02:21:21.089614+00:00`；首次加入協議的 commit 為 [37fa9923147c074a7130070eb44bb4b75eac67c6](https://github.com/skyful-sky/MarkSixGrok/commit/37fa9923147c074a7130070eb44bb4b75eac67c6)，author／committer 均為 `2026-10-29T10:23:33+08:00`（UTC `2026-10-29T02:23:33Z`）。`prereg-r3` 指此協議名稱；本庫沒有同名 Git tag。META JSON 的 `audit.code_commit` 記為 `59db40b3ebd6b4881393c1ae25b6848bb2450a5e`，不應與首次存入預測的 commit 混同。
- 本次透過已授權 GitHub 連線取得上述兩個預測 commit，並核實倉庫 `visibility=private`。這證實查核時已能在私人遠端讀取，不能倒推出首次 push 時間、特定 Manager 閱讀時間或公眾可見時間。獨立時間戳／公開存證／截止前公開 tag 證據：缺。

核對來源包括 [R2 commit REST](https://api.github.com/repos/skyful-sky/MarkSixGrok/commits/b27e50a23f29eae542514afc437ca0d58142e192)、[META commit REST](https://api.github.com/repos/skyful-sky/MarkSixGrok/commits/3e8081624fee35edb683373f7603ac895a82bb27)、[GitHub 倉庫](https://github.com/skyful-sky/MarkSixGrok)及本地 `git log --follow`、`git cat-file -p prereg-r2`。私人連結需要權限，不能當作公開存證。

## 與官方開獎／售票時間比較

[香港賽馬會 2026-10-27 公告](https://www.hkjc.com/english/pressrelease/mcs01_showhtml.asp?SelType=NEWS&filename=20261027_144259_E_NEWS.htm)本次重新讀取確認：萬聖節金多寶於 **2026-10-31 21:30 HKT**（13:30 UTC）攪珠，**21:15 HKT**（13:15 UTC）截止售票，10 月 29 日不設攪珠。這是排程公告，並非已發生的開獎結果或實際開獎時間存證。

公告沒有列出「26/116」期號。原 R2 JSON 的期號與日期對應引用第三方 `https://marksixinfo.com/`，META 延用該日期；**官方明列 26/116 與此日期對應的證據：缺**。本次不把第三方對應提升為官方核實，也沒有改動正式紀錄。

按原檔預定日期及公告時間比較，兩份紀錄的自載時間與 Git 時間都早於預定截止及開獎；查核當時亦尚未到公告日期。但**截止前公開預測／公開 tag 的可核證時間：缺**，不能把 Git 時間先後或私人 push 當作公開預註冊已通過。`prereg/round2.yaml` 的 `publication_verified: false`、原檔 `publication_unverified` 及 R3 的未核實狀態均保持不變。官方期號對應、實際開獎及最終有效性仍待證據，不宣告該輪通過或已完成評分。

## 內容雜湊核對

以下 SHA-256 由現存原始位元組重新計算，並與各自既有 `.sha256` 一致；同時確認當前內容與首次提交內容相同。payload 依原記錄定義：排除頂層 `audit`，UTF-8 JSON 使用 `ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False` 並加一個 LF。只重算既有內容的雜湊，沒有重跑出票方法。

| 紀錄 | 完整 JSON 檔案 SHA-256 | 不含 audit 的 payload SHA-256 |
|---|---|---|
| R2（H3＋H1） | `3476621fd81f14aca6403fbfc8a51e412fac3a5c46f85fe9f7ea5e1360384e3c` | `389a5930b4c024a54d32285423623e3ae5f6f69d33ebba823c9daff451fc5b9d` |
| META-BORDA | `56743ca4c6ff63867673aebc4d2b428a6ffcf0f01a6ca0bac163f5cbabd75c90` | `6598b8422001616cd11f3cab82888102d835388e73b3b633ae912eed942ca249` |

完整檔雜湊與 payload 雜湊涵蓋範圍不同，不應互換；雜湊本身亦不證明何時公開。

## 範圍、測試與交付

本次新增只有本文件及 `forward-record-audit.md.sha256`。H3／prereg-r2／prereg-r3、`marksix_data.csv`、正式 26/116、META 預測、所有出票程式及 `registry/attempts.csv` 均不修改；原有追蹤檔案逐位元組核對。既有 registry 23 筆含非模型紀錄，不等於 23 次嘗試；attempts 仍 **14/20，剩 6**，本次新增 0。

完整既有測試命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/marksix-r2-venv/bin/python -m pytest tests/ docs/review-evidence/test_signal_visibility_diag.py -q -p no:cacheprovider
```

測試結果：**96 passed in 5.52s**，全綠。未另行呼叫任何 `predict`、`evaluate` 或回測 CLI。

本文件的最終 SHA-256 見隨附 [校驗檔](forward-record-audit.md.sha256)，避免在文件內嵌自身雜湊。驗證方式：於 `docs/` 執行 `sha256sum --check forward-record-audit.md.sha256`。
