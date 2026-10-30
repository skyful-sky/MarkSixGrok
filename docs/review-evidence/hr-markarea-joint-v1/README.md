# HR-MARKAREA-JOINT-v1 資料閘門證據

只做來源／影像資格核查，沒有擬合、量測印記面積、計算命中率或新增attempt。結論見[報告](../../hr-markarea-joint-v1-data-gate.md)。

- `sources.json`：27個直接HTTP請求的來源、UTC取得時間、狀態、原始內容SHA-256及保存範圍。包含失敗／候選網址；不能把403、404當成資料不存在的證明。
- `source-snapshots.jsonl.gz`：12個成功頁面的原始回應位元組，無損gzip封裝JSONL，每列`raw_body_base64`解碼後的SHA-256須等於`response_sha256`。未把解析後文字冒作原文。其餘請求只留元資料；UK當前開獎表不收進本案資料。
- `images/`：4張未改動的原始資產；香港官方2016照片、日本官方機台照片、瑞穗機台插圖、英國博物館展示照片。保留插圖是為明確排除，不能當物理球照。影像著作權仍屬原來源，附件僅用於本次來源核查。
- `images.csv`：7個實際檢視資產的尺寸、類型、原始雜湊及失格理由；3張第三方圖片只留元資料，未鏡像保存。拍攝日期、實體球批及可用起訖均NA。頁面日期／HTTP Last-Modified不等於拍攝或歷史可得日期。
- `gate.json`：固定β先驗`N(0,0.25²)`、三地必要欄位缺口、封存決定；合資格區間空集合、0次擬合／回測／預測／attempt，累計14。
- `SHA256SUMS`及本目錄文件側檔：由庫根用`sha256sum -c docs/review-evidence/hr-markarea-joint-v1/SHA256SUMS`覆核，包含本次報告、A24所在lessons及附件。本輪Manager只准提交報告、本目錄與`docs/lessons.md`；因此沒有更新範圍外的`docs/lessons.md.sha256`或既有`docs/review-evidence/SHA256SUMS`，其中舊lessons雜湊代表修改前版本，不能當作目前A24版本的校驗。本次現行校驗以本目錄索引為準。

來源回應雜湊指HTTP內容解碼後的`response.content`；未把下載時間倒填為公開時間。直接請求使用TLS驗證，沒有登入或執行網站JavaScript／外部模型。來源核查程式只下載、雜湊、讀取影像尺寸及封裝附件，未讀封存結果或計算號碼分布。
