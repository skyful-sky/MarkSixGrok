"""Render tables from the sealed audit JSON only; never runs simulations."""

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "audits/AUD-SERIAL-K6-v1"
RUN = BASE / "run"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    results = json.loads((RUN / "results.json").read_text())
    seal = json.loads((RUN / "sealed.json").read_text())
    assert results["run_count"] == seal["run_count"] == 1
    assert digest(RUN / "results.json") == seal["results_sha256"]
    assert digest(BASE / "ledger.jsonl") == seal["ledger_sha256"]
    calibration = json.loads((RUN / "calibration.json").read_text())
    assert digest(RUN / "calibration.json") == results["calibration_file_sha256"]
    names = {"uk": "UK", "japan": "日本", "korea": "韓國"}
    stats = {"marginal_chi_square": "邊際χ²", "pair_max_absolute_z": "pair-max（絕對Z）",
             "positive_serial_overlap": "正向serial-overlap", "any_of_three": "任一主槽"}
    report = ["# AUD-SERIAL-K6-v1：一次外部集合依賴審計結果", "",
        "**決定：封存本審計。** UK與日本六個可計算主槽均未達九槽Bonferroni門檻，韓國三槽因不足暖身為NA；沒有候選通過、沒有香港回測申請。這是未見足夠審計證據，不能證明所有依賴為零或命中率路線不存在。香港命中嘗試仍14，既有最佳SH-GAP1 7/20仍屬探索；HR-TE維持reject、EV-COMP-NB-R3未運行。", "",
        "[預鎖文件](prereg/aud-serial-k6-v1.md)／[機讀參數](../audits/AUD-SERIAL-K6-v1/lock.json)／[程式](../src/aud_serial_k6_v1.py)／[測試](../tests/test_aud_serial_k6_v1.py)／[結果JSON](../audits/AUD-SERIAL-K6-v1/run/results.json)／[只追加台帳](../audits/AUD-SERIAL-K6-v1/ledger.jsonl)。", "",
        "## 執行與資料資格", "",
        f"預鎖並push：`{results['prereg_commit']}`；合成測試後鎖定實作並push：`{results['implementation_commit']}`。之後才執行唯一一次`--run`，run_count=1，沒有試跑真實窗口、重抽seed、重跑或按結果改規格。", "",
        f"開始UTC：`{results['started_at_utc']}`；完成UTC：`{results['completed_at_utc']}`。", "",
        "| 國家 | 暖身／評分 | 評分日期 | 完整性／限制 |",
        "|---|---|---|---|",
        f"| UK 6/49 | 701–900／901–1400；200＋500 | {results['observed']['uk']['score_first_date']}–{results['observed']['uk']['score_last_date']} | 本次所需700槽無缺；1401–1700未解析／分析 |",
        f"| 日本6/43 | 701–900／901–1146；200＋246 | {results['observed']['japan']['score_first_date']}–{results['observed']['japan']['score_last_date']} | 本次446槽無缺；1147起改制排除，不冒稱500 |",
        "| 韓國6/45 | 701–835僅135暖身；評分0 | NA | 少65暖身期，沒有借用封存窗口或延長截止 |", "",
        "來源、SHA-256與備用站URL均在機讀鎖；未新增或改寫數據。三國完整官方逐期核對、實體機球歷史及未曝光資格仍未核實；discovery既有曝光不因預鎖消失。本審計只在固定九槽內使用α=.0125，不重置先前選模的歷史成本。", "",
        "## 全部九槽：主檢定", "",
        "兩國各100,000次完整k-of-N IID虛無；PCG64種子20261030，三國索引及stream固定。p=(1+不少於觀測的次數)/100001，含同值；調整p=min(1,9p)，每槽門檻1/720≈.00138889，總α=.0125。pair-max每次在全體號碼對取最大，沒有再挑個別pair。韓國三槽保留，不挪α。", "",
        "| 國家 | 統計量 | 觀測值 | ≥觀測的MC次數 | 原始p | Bonferroni調整p | 結論 |",
        "|---|---|---:|---:|---:|---:|---|"]
    for slot in results["slots"]:
        if slot["status"] == "NA":
            cells = ["NA"] * 4 + ["不足暖身／NA"]
        else:
            value = slot["statistic_value"]
            cells = [f"{value:.6f}", str(slot["null_extreme_including_ties"]),
                     f"{slot['p_mc']:.8f}", f"{slot['p_bonferroni']:.8f}",
                     "顯著，僅審計訊號" if slot["significant"] else "未顯著"]
        report.append("| " + " | ".join([names[slot["country"]], stats[slot["statistic"]], *cells]) + " |")
    report += ["", "UK serial-overlap=394，相對公平期望367.346939，原始p≈.06214也未過單槽門檻，九槽調整後≈.55925；日本=205，相對期望205.953488。不能因UK是六槽中較小p而改成未校正通過。", "",
        "三項的共同H0為逐期獨立且各六碼集合均勻；它們不會單獨識別設備、因果機制或可預測方向。非均勻邊際本身也可提高平均相鄰重號，其他集合結構可改變統計量波動；不能把重號槽單獨稱作已控制所有其他結構的純serial檢定。", "",
        "## 先鎖合成功效：全部替代、全部強度", "",
        "每格5,000條完整序列，用同一九槽門檻及該國已保存的null樣本；未依功效挑選模型。下表是檢出率百分比，不是八注成功率；完整逐格計數、MC標準誤及95% Clopper–Pearson區間在[power.csv](review-evidence/aud-serial-k6-v1/power.csv)及[calibration.json](../audits/AUD-SERIAL-K6-v1/run/calibration.json)。區間條件於本次null校準池，不包含null門檻的MC不確定性，亦非同時信賴區間，不用來另篩勝者。", "",
        "| 國家 | 合成族／強度 | 邊際χ² % | pair-max % | 正向overlap % | 任一主槽 % |",
        "|---|---|---:|---:|---:|---:|"]
    power_rows = []
    for country in ["uk", "japan"]:
        for alternative in calibration[country]["power"]:
            label = f"{alternative['family']}／{alternative['strength']:g}"
            values = [f"{alternative['power'][key]['rate']*100:.2f}" for key in stats]
            report.append("| " + " | ".join([names[country], label, *values]) + " |")
            for key, power in alternative["power"].items():
                power_rows.append(dict(country=country, stream=alternative["stream"],
                    family=alternative["family"], strength=alternative["strength"], statistic=key,
                    replicates=power["replicates"], detected=power["detected"], rate=power["rate"],
                    mc_se=power["mc_se"], ci95_low=power["clopper_pearson_95"][0],
                    ci95_high=power["clopper_pearson_95"][1]))
    report += ["", "例如保留一碼ρ=.10的正向overlap檢出率UK22.66%、日本7.32%；ρ=.25時99.48%／75.52%。弱替代可能難以檢出，日本短窗更受限；不能將無顯著外推為所有微弱依賴都不存在。環形聚集保持各號邊際6/N但改變聯合集合，亦說明邊際均勻不等於完整集合公平；任何審計功效均不等於真實八注勝率。", "",
        "## 附報：間隔幾何與Phi（不選通過者）", "",
        "| 完整間隔g | UK次數 | UK單號公平幾何概率 | 日本次數 | 日本單號公平幾何概率 |",
        "|---|---:|---:|---:|---:|"]
    gaps = {c: results["observed"][c]["appendices"]["gap_geometric"] for c in ["uk", "japan"]}
    for i, label in enumerate(gaps["uk"]["bins"]):
        report.append(f"| {label} | {gaps['uk']['counts'][i]} | {gaps['uk']['iid_single_number_geometric_probabilities'][i]:.8f} | {gaps['japan']['counts'][i]} | {gaps['japan']['iid_single_number_geometric_probabilities'][i]:.8f} |")
    report += ["", "UK完整間隔3000、日本1476；兩者評分命中左設限均0，窗尾各49／43號仍作右設限列帳，未當完整間隔。池化、有限窗及設限不支持把各間隔當獨立幾何樣本；沒有額外p、調bin或選勝。", "",
        "Phi文獻原檢定及原碼未完整取得，重現狀態**NA**。附報只有預鎖的描述性Pearson Φ divergence：六碼和值的暖身四分位symbol、lag1 4×4表；不冒稱maximum Phi-entropy論文檢定，無p、不占第十槽。", ""]
    for country in ["uk", "japan"]:
        phi = results["observed"][country]["appendices"]["phi_descriptive_only"]
        report += [f"{names[country]}：切點`{phi['warmup_quantile_cuts']}`，Φ=`{phi['value']:.12f}`；相鄰類別次數表（列為前期、欄為本期）：", "", "```text"]
        report += [" ".join(map(str, row)) for row in phi["lag1_counts"]]
        report += ["```", ""]
    report += ["韓國兩項附報均NA，沒有拿135期代替完整暖身及評分。", "",
        "## Random參考、封存及執行紀錄", "",
        "沿用既有均勻排序環繞八注模板，只有公平配置參考，**未生成／回測Random或HR-TE八注**。UK14.829943%、日本20.029529%（約20.03%，非21.5%）、韓國18.549771%。這些是命中率配置基準，不是本審計的顯著性門檻；沒有新命中率估計或EV結論。", "",
        "無主槽通過，依預鎖封存AUD-SERIAL-K6-v1，不復活HR-TE，也沒有另提或實作聯合預測模型。兩國外部逐期八注門檻未通過，不申請香港回測；即使未來另有審計訊號，也須另行完整規格與授權。", "",
        "兩國各100,000次null、11格×5,000次power，共310,000條完整序列；24份NPZ保存全部replicate的三個整數統計量，calibration.json保存1,222批抽樣雜湊、stream及RNG終態。未保存十億餘模擬球號，但可用已鎖程式／環境與每批雜湊核查生成過程；不提供重跑選項或按結果續跑。", "",
        f"results.json SHA-256：`{digest(RUN / 'results.json')}`。", "",
        "全套測試／保護檔核對見[最終驗證](review-evidence/aud-serial-k6-v1/validation-final.json)，執行前驗證為262通過／28跳過（27封存讀取＋1尚未產生結果）。執行後會驗證已封存結果而不啟動新run。新檔校驗索引見`audits/AUD-SERIAL-K6-v1/SHA256SUMS`；既有保護檔、registry條目、tags及sealed windows不動。", "",
        "此報告由[轉錄程式](review-evidence/aud-serial-k6-v1/render_report.py)只讀已封存JSON產生，沒有新模擬、擬合或候選評分。"]
    (ROOT / "docs/aud-serial-k6-v1-results.md").write_text("\n".join(report) + "\n")
    with (Path(__file__).parent / "power.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(power_rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(power_rows)
    (Path(__file__).parent / "report-source.json").write_text(json.dumps({
        "renderer": "render_report.py", "input_results_sha256": digest(RUN / "results.json"),
        "input_calibration_sha256": digest(RUN / "calibration.json"),
        "report_sha256": digest(ROOT / "docs/aud-serial-k6-v1-results.md"),
        "power_csv_sha256": digest(Path(__file__).parent / "power.csv"),
        "new_simulations": 0, "new_fits": 0, "new_candidate_scores": 0}, indent=2) + "\n")


if __name__ == "__main__":
    main()
