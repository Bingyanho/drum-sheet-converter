# Video Sheet Converter 快速使用說明

把影片中的樂譜、講義、文件頁面轉成 JPG / PDF。

## 1. 開啟程式

雙擊 `VideoSheetConverter.exe`，或使用資料夾中最新的 `VideoSheetConverter_v*.exe`。

第一次開啟比較慢是正常的。

## 2. 基本流程

1. 在 `Video or URL` 選影片，或貼上 YouTube 連結。
2. 在 `Output name` 輸入輸出名稱。
3. 選擇模式：`rows` 或 `scroll`。
4. 按 `Select Area and Convert`。
5. 框選影片中的內容區域。
6. 按 Enter 或 Space 確認。
7. 完成後按 `Open Output` 看 PDF。

## 3. rows 還是 scroll？

選 `rows`：

- 畫面一段一段更新
- 樂譜、講義、題目逐段出現
- 想擷取多張畫面再合成 PDF

選 `scroll`：

- 整張頁面一直往下捲
- 內容上下是連續的
- 想拼成長圖後切成 PDF

## 4. 框選技巧

- 只框選真正要輸出的內容。
- 不要框到播放器按鈕、字幕、黑邊。
- 可以留一點空白，但不要留太多。
- 框選錯了按 `R` 重新選。

## 5. 常用選項

`Review captured images before creating PDF`

rows 模式可用。輸出前逐張檢查，不要的圖片按 `D` 刪除。

`Delete downloaded video after conversion`

建議保持開啟。使用 YouTube 連結時，轉換成功後會自動刪除下載影片，避免占空間。

## 6. Advanced settings 什麼時候要調？

平常不用調。遇到下面情況再打開。

漏抓畫面：

```text
Rows interval: 0.5
Capture threshold: 2.0
```

還是漏抓：

```text
Rows interval: 0.25
Capture threshold: 1.0
```

抓到太多重複畫面：

```text
Capture threshold: 4.0 或 5.0
```

scroll 拼接容易斷：

```text
Scroll interval: 0.35
Scroll match score: 10
New content diff: 3.5
```

scroll 的最大位移會自動使用「框選高度 - 50」，最小位移固定為 8，通常不用調。

## 7. YouTube 下載失敗怎麼辦？

如果 YouTube 要求登入、確認不是機器人，或下載失敗：

1. 先用瀏覽器或其他工具下載成 MP4。
2. 回到程式選擇本機 MP4。
3. 再轉換。

這樣最穩。

## 8. 輸出檔在哪裡？

轉換完成後按 `Open Output`。

資料夾裡會有：

- `.jpg` 圖片頁面
- `.pdf` 文件
- 如果有開 report，會有 `report.json`

## 9. 建議

第一次處理新影片時，先用預設值跑一次。

如果結果不理想：

- 漏抓：降低 `Rows interval` 或 `Capture threshold`
- 抓太多：提高 `Capture threshold`
- scroll 接不上：降低 `Scroll interval`
