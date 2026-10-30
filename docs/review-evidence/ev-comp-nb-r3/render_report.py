"""Transcribe sealed R3 JSON/scores into a report; no fit, score or simulation."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HOME=ROOT/'ev/EV-COMP-NB-R3'
RUN=HOME/'run'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result=json.loads((RUN/'results.json').read_text())
    seal=json.loads((RUN/'sealed.json').read_text())
    assert result['run_count']==seal['run_count']==1
    assert sha(RUN/'results.json')==seal['files_sha256']['results.json']
    assert sha(HOME/'ledger.jsonl')==seal['ledger_sha256']
    scores=[json.loads(line) for line in (RUN/'scores.jsonl').read_text().splitlines()]
    zeros=Counter(r['country'] for r in scores for y in r['count_values'] if y==0)
    names={'uk':'UK','japan':'日本'}
    comparisons={r['country']:r for r in result['primary_comparisons']}
    report=['# EV-COMP-NB-R3：固定外部窗口逐期計數評分結果','',
      '**兩國計數預測均勝Random並通過預鎖名義篩選；財務指標不可評估，整版結果封存。** 計數log-score優勢不等於條件派彩比≥1.10、正EV、香港命中優勢或確認性證據。沒有出票、cashflow計算、香港回測或AUD-SERIAL重跑。','',
      '[原預鎖](prereg/ev-comp-nb-r3.md)／[實作鎖說明](ev-comp-nb-r3-implementation.md)／[程式](../src/ev_comp_nb_r3.py)／[測試](../tests/test_ev_comp_nb_r3.py)／[結果JSON](../ev/EV-COMP-NB-R3/run/results.json)／[封存校驗](../ev/EV-COMP-NB-R3/run/sealed.json)。','',
      '## 先鎖後跑及資料範圍','',
      f"原預鎖commit `{result['prereg_commit']}`。Manager於2026-10-30 18:05 HKT明示授權後，先以合成fixture核對，再commit及push實作 `{result['implementation_commit']}`，才作唯一一次真實運行。run_count=1，不改原預鎖或參數、不重試、不按結果換窗。",'',
      f"開始UTC `{result['started_at_utc']}`；完成UTC `{result['completed_at_utc']}`（HKT 2026-10-30 18:19–18:21）。",'',
      '| 國家 | 暖身 | 固定逐期評分 | 更新次數／三模型擬合 | 全部六碼集合／精確特徵類 |',
      '|---|---|---|---:|---:|']
    for country in ['uk','japan']:
        c=result['countries'][country]
        period='901–1400' if country=='uk' else '901–1146'
        report.append(f"| {names[country]} | 701–900，200期 | {period}，{c['valid_paired_score_n']}期 | {c['updates_completed']}／{c['updates_completed']*3} | {c['exact_universe_size']:,}／{c['exact_feature_classes']:,} |")
    report += ['', 'UK25次、日本13次更新，合計114次R3／Random／靜態模型擬合均收斂；日本不跨1147制度切點，不冒稱500期。首次901前用701–900，其後每20原期號擴展更新，區塊內凍結；每次同一起點theta=0、r=30與原L-BFGS-B容限。', '',
      '資料只用預鎖EV1快照。先保存參數、歷史截止、銷量預測及SHA收據，再由broker揭示目標期球號／注數，評分後才加入歷史。這證明本次計算的順序，並非在歷史開獎前公開發表；來源與discovery既有曝光不消失。', '',
      '## Random主比較：名義計數門檻通過','',
      '每期先在兩模型共同可比較獎級格平均NB2 log probability，再跨期平均；較高（較不負）較好。Random是均勻組合的含零NB2，與R3共用只用既往更新的銷量預測、遮罩及更新日，並非抽八張票的噪聲基線。','',
      '| 國家 | n | R3平均分數 | Random平均分數 | R3−Random | 單側98.75% basic下界 | p | 計數門檻 |',
      '|---|---:|---:|---:|---:|---:|---:|---|']
    for country in ['uk','japan']:
        c=result['countries'][country];x=comparisons[country]
        report.append(f"| {names[country]} | {x['n']} | {c['mean_scores']['r3']:.9f} | {c['mean_scores']['random']:.9f} | {x['mean_log_score_gain']:.9f} | {x['lower_9875']:.9f} | {x['p_value']:.9f} | {'通過' if x['pass_count'] else '未過'} |")
    report += ['', '固定循環moving-block bootstrap：block10、10,000次、PCG64種子20261030，國家／用途分流；p=(1+不少於觀測增益的置中bootstrap次數)/10001。兩國均n≥200、平均差>0、下界>0、p≤.0125。這是**預鎖的探索性名義篩選**；先前R1四比較與本版兩主比較全數保留，不能藉更名重置FWER=.05，亦不聲稱跨版本確認性錯誤率已受控。', '',
      '## 次要基準：只描述，不另選勝者','',
      '| 國家 | R3−單一≤31靜態偏好平均差 | R3−封存R1同格平均差 | 次要p |',
      '|---|---:|---:|---|']
    for country in ['uk','japan']:
        s=result['countries'][country]['descriptive_secondary']
        report.append(f"| {names[country]} | {s['R3_minus_static_mean']:.9f} | {s['R3_minus_sealed_R1_same_cell_mean']:.9f} | NA／不檢定 |")
    report += ['', 'R1逐級分數直接重用封存檔，沒有重擬合。R1與R3的更新規則亦不同，此描述差異不能全歸因於新增特徵，不取代Random主比較或重判R1原先封存結果。', '',
      '## 缺值、零值及財務停止條件','',
      '| 國家 | 有效獎級計數格 | 缺計數格 | 保留的零值格 | 缺歷史公告時間期數 | 缺完整法律版本期數 |',
      '|---|---:|---:|---:|---:|---:|']
    for country in ['uk','japan']:
        c=result['countries'][country];f=c['financial_gate']
        report.append(f"| {names[country]} | {c['observed_count_cells']} | {c['missing_count_cells']} | {zeros[country]} | {f['missing_original_announcement']} | {f['missing_complete_legal_version']} |")
    report += ['', '上述缺格是注數缺格，不是所有財務欄位的NA總數；來源衝突及其他NA均維持原CSV。缺計數只遮罩原格、沒有補值／刪零／對Y取log或補入別期；746期都有至少一個可比較獎級。模型銷量預測另存為預測值，沒有補寫原來源NA。', '',
      '條件派彩比、校正下界、ROI下界全部**NA**：歷史法律版本／公告時刻未完整核實，也沒有另鎖完整出票／cashflow及加入自身投注後的分彩、成本、保底／封頂計算。不能把log-score增益換成派彩百分比、用實際派彩乘本方注數反推，或把結果旗標positive_ev=false解讀為已證明真實EV為負；它只表示本次沒有正EV通過聲稱。', '',
      '**判定：兩國計數名義篩選通過；派彩／正EV門檻不可評估，整體passed=false、status=archived。** 封存是保留本次完整結果，不抹掉計數改善；後續財務工作仍須另鎖規格與授權，不能直接出票。', '',
      '## 精確性、留帳與保護','',
      '七個特徵只各定義一次，無滾存交互項、無電腦票混合omega；Ω只是整數組合重數。非加性十位／間距熵採完整枚舉後的精確類別重數，沒有用單號ESP或MC代替；各獎級鄰域也保留整數重數並共用Z。每次更新、精確類別／已揭示稀疏投影、746份參數／銷量收據、逐期逐級分數及bootstrap置中統計均保存。', '',
      f"results.json SHA-256：`{sha(RUN/'results.json')}`。", '',
      '前測278通過、28跳過；執行後完整測試及保護項核對見[最終驗證](review-evidence/ev-comp-nb-r3/validation-final.json)。27項封存讀取舊測試依Manager限制跳過，不冒稱已執行。', '',
      'H3、prereg-r2/r3、marksix_data.csv、正式26/116、registry既有條目、tags、sealed windows、R1與AUD-SERIAL封存全保留；AUD-SERIAL沒有重跑。新命中嘗試0，累計仍14，SH-GAP1既有7/20不因EV計數改善而改判。', '',
      '文件／實作／結果校驗索引為`ev/EV-COMP-NB-R3/SHA256SUMS`。本報告由[轉錄程式](review-evidence/ev-comp-nb-r3/render_report.py)只讀已封存輸出產生，不重新擬合、評分或bootstrap。']
    path=ROOT/'docs/ev-comp-nb-r3-results.md';path.write_text('\n'.join(report)+'\n')
    (Path(__file__).parent/'report-source.json').write_text(json.dumps(dict(
      input_results_sha256=sha(RUN/'results.json'),input_scores_sha256=sha(RUN/'scores.jsonl'),
      report_sha256=sha(path),new_fits=0,new_scores=0,new_bootstrap_replicates=0),indent=2)+'\n')


if __name__=='__main__':main()
