# 26/116 前向紀錄：OpenTimestamps 提交

基準 commit：`ef44fbdd982e4befeb49d89252589451febeac0f`。本次只為既有內容建立外部時間戳收據；不改原檔、不產生預測、不回測、不新增 ID。attempts 仍 **14/20，剩 6**。

## 結果及證明範圍

`ots stamp` 於本機記錄的 **2026-10-29 05:07:40.242750–05:07:48.419041 UTC**（**13:07:40.242750–13:07:48.419041 HKT**）執行，退出碼 0，產生下列三個 `.ots`。這是提交操作的本機時間，並非已獲獨立核證的 Bitcoin 區塊時間。

所有證明保存於 [docs/review-evidence/timestamps/](review-evidence/timestamps/)。透過 `ots info` 及用戶端解碼確認，每個 `.ots` 的 SHA-256 摘要與原檔吻合，均含三個 `PendingAttestation`，**沒有 `BitcoinBlockHeaderAttestation`**。目前狀態為「calendar 收據成功；Bitcoin 錨定及獨立驗證待完成」，不是 `ots verify` 通過。本次未執行 `ots upgrade` 或 `ots verify`；下方列明後續步驟。

| 被時間戳的既有檔案 | SHA-256 | `.ots` |
|---|---|---|
| [R2：H3／H1](../forward/26-116.prediction.20261029T001900Z.json) | `3476621fd81f14aca6403fbfc8a51e412fac3a5c46f85fe9f7ea5e1360384e3c` | [26-116.prediction.20261029T001900Z.json.ots](review-evidence/timestamps/26-116.prediction.20261029T001900Z.json.ots) |
| [META-BORDA](../forward/meta-borda/26-116.prediction.20261029T022640Z.json) | `56743ca4c6ff63867673aebc4d2b428a6ffcf0f01a6ca0bac163f5cbabd75c90` | [26-116.prediction.20261029T022640Z.json.ots](review-evidence/timestamps/26-116.prediction.20261029T022640Z.json.ots) |
| [既有前向紀錄審查](forward-record-audit.md) | `041ef1de1976ff76fa2e3e9e076496417f3cf80f45f7e165f243084a2fba4568` | [forward-record-audit.md.ots](review-evidence/timestamps/forward-record-audit.md.ots) |

前兩個證明直接綁定預測檔案的 SHA-256；第三個綁定原審查文件的全部內容，連同其所列完整檔案、payload 及訓練快照 SHA-256。不是把十六進位雜湊文字當作原檔再次雜湊；不應把 payload 雜湊誤當完整預測檔摘要。本次使用位元組相同的暫存副本執行標準 `ots stamp`，只將產出的 `.ots` 移入本庫，原檔保持不變。

## Calendar 回應

四個預設提交端點均出現在原始輸出：

```text
Doing 2-of-4 request, timeout is 15 seconds
Submitting to remote calendar https://a.pool.opentimestamps.org
Submitting to remote calendar https://b.pool.opentimestamps.org
Submitting to remote calendar https://a.pool.eternitywall.com
Submitting to remote calendar https://ots.btc.catallaxy.com
<urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1029)>
8.01 seconds elapsed
```

每個 `.ots` 中實際保存的待確認 calendar URI 相同：

| 證明內 URI | 狀態／原文 |
|---|---|
| `https://alice.btc.calendar.opentimestamps.org` | 成功取得 `PendingAttestation('https://alice.btc.calendar.opentimestamps.org')` |
| `https://bob.btc.calendar.opentimestamps.org` | 成功取得 `PendingAttestation('https://bob.btc.calendar.opentimestamps.org')` |
| `https://finney.calendar.eternitywall.com` | 成功取得 `PendingAttestation('https://finney.calendar.eternitywall.com')` |

CLI 同時報一則 SSL EOF 失敗；該錯誤行沒有端點標籤，故失敗端點的直接歸屬證據為「缺」，不把它推定為特定服務。提交池 URL 與收據 URI 分別照原文保留。退出碼 0 表示本次達到預設至少兩個 calendar 回覆的要求；三個收據仍全部 pending，不代表三次已確認的 Bitcoin 證明。

原文及結構化紀錄：[stamp.log](review-evidence/timestamps/stamp.log)、[info.log](review-evidence/timestamps/info.log)、[submission.json](review-evidence/timestamps/submission.json)。`submission.json` 包含提交時間、完整命令、原檔／證明 SHA-256、各 attestation 類別、URI 及承諾值。三檔在同一批次提交，共用 calendar 承諾分支；它們不是三次獨立時間認證。

## 安裝與實際指令

用戶端安裝在獨立環境，沒有改 `requirements.txt` 或 R2 測試環境：

```bash
python3 -m venv /tmp/marksix-ots-venv
/tmp/marksix-ots-venv/bin/python -m pip install opentimestamps-client
/tmp/marksix-ots-venv/bin/ots --version
```

實際安裝版本為 `opentimestamps-client==0.8.0`、`opentimestamps==0.5.0`；完整相依版本見 [client-freeze.txt](review-evidence/timestamps/client-freeze.txt)。安裝成功。Python 版 0.8.0 沒有 `stamp-digest` 子命令，本次使用其標準檔案介面。

實際暫存目錄為 `/tmp/marksix-ots-ugntxn61/`，以 `shutil.copyfile` 複製以下三個既有檔案；提交命令如下（完整參數亦保存在 `stamp.log`）：

```bash
/tmp/marksix-ots-venv/bin/ots --no-cache -v stamp --timeout 15 \
  /tmp/marksix-ots-ugntxn61/26-116.prediction.20261029T001900Z.json \
  /tmp/marksix-ots-ugntxn61/26-116.prediction.20261029T022640Z.json \
  /tmp/marksix-ots-ugntxn61/forward-record-audit.md
```

程式把三個新 `.ots` 移到 `docs/review-evidence/timestamps/`，再對每個證明執行 `/tmp/marksix-ots-venv/bin/ots info <證明路徑>`，三次退出碼均為 0。沒有使用 Bitcoin 錢包或發送自行付款交易。

## 日後 upgrade／verify

等待 calendar 完成 Bitcoin 錨定及確認後，在本庫根目錄執行。先保存現有收據；`upgrade` 可修改 `.ots` 並建立 `.bak`，後續改動需另行 commit，不能覆寫原始預測或倒填提交日期。不要使用 `--wait` 無限等待；未完成便保留 pending，日後重試。

```bash
/tmp/marksix-ots-venv/bin/ots --no-cache upgrade --timeout 15 \
  docs/review-evidence/timestamps/26-116.prediction.20261029T001900Z.json.ots \
  docs/review-evidence/timestamps/26-116.prediction.20261029T022640Z.json.ots \
  docs/review-evidence/timestamps/forward-record-audit.md.ots
```

`ots info` 出現 Bitcoin attestation 仍須驗證。以下命令以 `-f` 指明原檔，因證明與原檔不在同一目錄：

```bash
/tmp/marksix-ots-venv/bin/ots verify --timeout 15 \
  -f forward/26-116.prediction.20261029T001900Z.json \
  docs/review-evidence/timestamps/26-116.prediction.20261029T001900Z.json.ots
/tmp/marksix-ots-venv/bin/ots verify --timeout 15 \
  -f forward/meta-borda/26-116.prediction.20261029T022640Z.json \
  docs/review-evidence/timestamps/26-116.prediction.20261029T022640Z.json.ots
/tmp/marksix-ots-venv/bin/ots verify --timeout 15 \
  -f docs/forward-record-audit.md \
  docs/review-evidence/timestamps/forward-record-audit.md.ots
```

也可用 `verify -d <上表的完整檔案 SHA-256> <證明路徑>`。依[官方 Python 用戶端說明](https://github.com/opentimestamps/opentimestamps-client)，Bitcoin 驗證需要可用的 Bitcoin Core 節點（可剪枝）；須設定本地節點或 `--bitcoin-node`。節點不可用、摘要不符或 calendar 未完成時，原樣保存錯誤，不得把 `--no-bitcoin`、`ots info` 或成功 `stamp` 當作 Bitcoin 驗證通過。

只有驗證完成後，才另存驗證命令、完整輸出、退出碼、Bitcoin 區塊高度及所證明的時間上界，再與原官方售票截止及開獎排程比較。這次新提交不能追溯證明原 JSON 自載時間或原 Git commit 的公開時間，也不代表預測內容曾對公眾開放；原協議的公開預註冊有效性不得自動改為已核實。

## 驗收與校驗

只新增本說明、同名 `.sha256` 及 `review-evidence/timestamps/` 證據；全部原有追蹤檔案逐位元組不變，包括 H3／prereg-r2／prereg-r3、CSV、兩份 26/116 預測、原前向審查及 registry。annotated tag `prereg-r2` 不變。

完整既有測試：`PYTHONDONTWRITEBYTECODE=1 /tmp/marksix-r2-venv/bin/python -m pytest tests/ docs/review-evidence/test_signal_visibility_diag.py -q -p no:cacheprovider`；結果 **96 passed in 6.47s**，全綠。

本文件 SHA-256 見 [forward-timestamps.md.sha256](forward-timestamps.md.sha256)。證據校驗清單見 [timestamps/SHA256SUMS](review-evidence/timestamps/SHA256SUMS)，於該目錄執行 `sha256sum --check SHA256SUMS`；本文件則於 `docs/` 執行 `sha256sum --check forward-timestamps.md.sha256`。日後升級 `.ots` 必須同步更新相關校驗與狀態說明。
