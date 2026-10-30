# INTRADRAW v2：兩案預鎖與合成數值驗收

本次完成Manager指定的步驟一：**HR-INTRADRAW-EXCLUSION-v2**及**HR-INTRADRAW-ATTRACT2-v2**預鎖、數學核與合成測試。外部擬合0、外部評分0、新香港命中嘗試0，累計仍14；沒有使用香港資料擬合新案，也沒有修改任何既有封存結果。

| 交付 | 路徑 |
|---|---|
| 共同完整規格 | [common.md](../prereg/intradraw-v2/common.md) |
| 秩2固定大小k-DPP | [exclusion.md](../prereg/intradraw-v2/exclusion.md) |
| 等邊際HS吸引模型 | [attract2.md](../prereg/intradraw-v2/attract2.md) |
| 機讀參數／指紋 | [lock.json](../prereg/intradraw-v2/lock.json) |
| 兩國各64套固定置換／單一起點 | [permutations.json](../prereg/intradraw-v2/permutations.json)、[initial-U.json](../prereg/intradraw-v2/initial-U.json) |
| 新附件預留j2／j3的四彩票槽 | [external-slots.csv](../prereg/intradraw-v2/external-slots.csv)；不改既有registry |
| 數學核與合成測試 | [intradraw_v2.py](../src/intradraw_v2.py)、[test_intradraw_v2.py](../tests/test_intradraw_v2.py) |
| Astra來源及數值證據 | [Astra final](review-evidence/intradraw-v2/astra-final.json)、[合成驗算](review-evidence/intradraw-v2/synthetic-validation.json)、[可重現合成程式](review-evidence/intradraw-v2/validate_synthetic.py) |

## 已鎖規格

兩案每列U的L2範數≤1、無盒約束、無極角排序；聯合負log likelihood總和＋||U||F²/2，固定非零單一起點，外層投影梯度最多1000接受步。內層從零解等邊際與Σlog權重=0的gauge，最多100步，計算殘差≤5e-12且加數值預算後最大誤差≤1e-10；未收斂或誤差核查失敗即封存，不重啟改參。

暖身只用UK／日本701–900各200期，擬合一次凍結；評分UK901–1400共500、日本901–1146僅246期篩選，韓國不用。64套原模板候選按模型完整聯集p8選一次，已證同值取最前；數值誤差區間無法判定最高者即停止，不拿近似同值冒充真同值。Random使用同配置與同64候選下的均勻模型，因全數同值而固定取第1套。

日本第8注位置為{43,1,2,3,4,5}，保留與第1注的五碼重疊。EXCLUSION與ATTRACT2的U=0分支均精確返回UK **12344/83237＝14.8299434146%**、日本 **1221091/6096454＝20.0295286407%**；浮點顯示不取代精確Fraction。

外部j1已由原校準佔用，因此新附件預留j2、j3，按`.05/[4j(j+1)]`分別為每彩票1/480、1/960；四槽都保留、未用者不重分配。通過須同時滿足原公平率q＋至少2個百分點、預留α下的上尾p與單側下界，以及原窗口／資料／穩定性要求。日本246期只可作部分篩選，不可當成500期資格或另一模型的獨立重現。

## 數值驗算及誤差範圍

- DP保留選取數≤6及每注命中截頂3，成功後合併為等價吸收狀態；同一球屬多注時同時更新，沒有假設各注獨立。EXCLUSION用秩2主子式矩展開接DP，另由完整主行列式窮舉核對。
- ATTRACT2主求積每軸64、共4096點，固定80×80只核查；解析理想求積截斷相對上界為7.9217420e-17，並另留5e-12浮點工程驗收預算。64／80的Z、π、p8差各有固定上限，超限停止，不換階數。一般求積不是零誤差。
- 8球取4的兩個**人工參數例子**：EXCLUSION最大等邊際殘差4.70e-14、p8與窮舉差2.78e-16；ATTRACT2分別7.24e-14及5.55e-17。這只是列明合成驗算的誤差，不把樣本誤差當成一般模型的全域證明。
- 另有8球取3的獨立窮舉、43／49球零U與同列合成U的Z／π核對、旋轉反射、配對偏差補償、64套公平同值取首、數值不明確時停止，以及圓盤浮點邊界案例。未以真實暖身資料調整任何規格。

完整回歸：**313通過、27跳過、0失敗**（25.26秒）；其中新數學核34項全數通過，27跳過為既有封存結果讀取隔離。命令與保護項核對另存[validation-final.json](review-evidence/intradraw-v2/validation-final.json)。既有回歸僅驗證原程式；本案合成驗算程式另裝檔案guard，拒絕歷史data、香港CSV及舊EV／審計／前向結果輸入。

## 尚未驗證的界線

所有統計／數值參數與停止規則均已鎖定，沒有待結果決定的自由項。**但全規模非零參數擬合／64候選效能沒有跑過，外部來源的完整官方及未曝光資格仍未核實；浮點工程預算也不是形式區間算術證書。** 本輪不聲稱已通過外部執行／確認性資格，更不聲稱兩模型已有物理證據。未來若另獲執行授權仍須遵守指紋、數值停止及外部來源規則，不能以本輪通過測試代替未完成驗證。

H3、prereg-r2/r3、marksix_data.csv、26/116、registry既有條目、tags、sealed windows及所有既有封存結果均未變；新文件校驗從庫根執行`sha256sum -c prereg/intradraw-v2/SHA256SUMS`。
