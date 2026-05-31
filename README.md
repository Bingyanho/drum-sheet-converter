# Video Sheet Converter

把影片中的樂譜、講義、文件頁面或其他白底內容擷取出來，轉成可列印的 JPG / PDF。

這個工具適合處理「內容在影片中變動，但你想留下乾淨頁面」的情境，例如動態樂譜、逐列更新的譜面、往下捲動的文件頁面、教學影片中的固定版面截圖。

## 功能特色

- 支援本機影片，也可以貼上 YouTube / web URL。
- 手動框選要擷取的內容區域，避免抓到播放器介面或背景。
- `rows` 模式：擷取一列一列變化的畫面。
- `scroll` 模式：拼接連續往下捲動的長頁面，再自動切成 A4。
- 自動輸出 JPG 頁面與 PDF。
- YouTube 下載預設限制在 1080p 或以下，避免影片太大造成轉換變慢。
- 轉換成功後預設刪除下載影片，節省空間。

## 專案檔案

- `drum_gui.py`：圖形介面，推薦一般使用者使用。
- `drum_auto.py`：命令列工具與主要影像處理邏輯。
- `requirements.txt`：Python 套件需求。
- `run_gui.bat`：Windows 一鍵啟動 GUI。
- `.gitignore`：排除下載影片、輸出結果、快取與打包檔。

執行後可能產生 `downloads/`、`sheet/`、`build/`、`dist/` 等資料夾，這些不需要提交到 GitHub。

## 安裝

建議使用 Python 3.10 或更新版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 使用 GUI

```powershell
python .\drum_gui.py
```

Windows 使用者也可以直接雙擊：

```text
run_gui.bat
```

基本流程：

1. 選擇本機影片，或貼上 YouTube URL。
2. 輸入輸出名稱。
3. 選擇轉換模式。
4. 按下 `Select Area and Convert`。
5. 在預覽視窗中拖曳框選內容區域，按 Enter 或 Space 確認。
6. 等待輸出完成，按 `Open Output` 查看 JPG / PDF。

## 轉換模式

`rows` 適合：

- 畫面是一列或一段內容在更新。
- 影片每隔一段時間換成新的譜面、題目、文件區塊。
- 你想擷取多張獨立畫面，再排成 A4 PDF。

`scroll` 適合：

- 整張頁面連續往下捲動。
- 內容上下相接，想先拼成一張長圖。
- 最後希望自動切成多頁 A4。

## 常用參數

- `--interval`：每隔幾秒掃描一次影片。數值越小越不容易漏抓，但速度較慢。
- `--threshold`：擷取門檻。預設 `3.5`。數值越低越容易保留小變化；數值越高越容易略過相似畫面。
- `--roi-time`：指定用影片第幾秒作為框選預覽畫面。大影片建議指定，會比較快跳出框選視窗。
- `--review`：輸出 PDF 前逐張檢查擷取結果，僅適用 `rows` 模式。
- `--report-json`：輸出處理統計資料。
- `--delete-temp`：輸出後刪除中間截圖。
- `--keep-downloaded-video`：保留從 YouTube / web URL 下載的影片。

`scroll` 模式進階參數：

- `--scroll-min-score`：拼接時允許的最大對齊誤差，預設 `10.0`。
- `--scroll-min-content-diff`：新接上的內容至少要和前一張有多少差異，避免只因為重疊區剛好能對齊就誤接。

scroll 模式會自動把最大位移設成「框選高度減 50」，最小位移固定為 8，一般使用者不需要調整。

## 命令列範例

一般 `rows` 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name output_name --mode rows --review
```

`rows` 模式如果容易漏抓：

```powershell
python .\drum_auto.py .\video.mp4 --name output_name --mode rows --interval 0.25 --threshold 1.0 --review
```

一般 `scroll` 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name output_name --mode scroll --interval 0.35
```

`scroll` 模式如果捲動速度較快：

```powershell
python .\drum_auto.py .\video.mp4 --name output_name --mode scroll --interval 0.2 --scroll-min-score 10 --scroll-min-content-diff 3.5
```

YouTube URL：

```powershell
python .\drum_auto.py "https://youtu.be/example" --name output_name --mode rows
```

如果 YouTube 顯示需要登入或確認不是機器人，建議先用瀏覽器或其他下載工具把影片存成 MP4，再用本機影片檔轉換。這樣最穩，也不會受到瀏覽器 cookies 鎖定影響。

## 打包成 EXE

安裝 PyInstaller：

```powershell
python -m pip install pyinstaller
```

打包單一 exe：

```powershell
python -m PyInstaller --onefile --windowed --name VideoSheetConverter .\drum_gui.py
```

輸出檔會在：

```text
dist\VideoSheetConverter.exe
```

單一 exe 啟動時會先解壓縮，速度會比直接跑 Python 慢。若要更快啟動，可以改用資料夾版打包：

```powershell
python -m PyInstaller --windowed --name VideoSheetConverter .\drum_gui.py
```

## 常見問題

框選視窗沒有立刻跳出：

大影片或高解析度影片需要先讀取預覽 frame。可以在 Advanced settings 的 `Crop preview time` 填入一個確定有內容的秒數，例如 `80`。

轉換太慢：

降低影片解析度、增加 `--interval`，或先手動下載 1080p 影片再轉換。程式內建 YouTube 下載已優先限制在 1080p 或以下。

漏抓畫面：

降低 `--interval`，例如 `0.25`；或降低 `--threshold`，例如 `1.0`。

抓到太多相似畫面：

提高 `--threshold`，例如 `4.0` 或 `5.0`。

scroll 模式切頁剛好切到同一行：

程式會在切 A4 時嘗試避開深色內容較多的位置，但如果原始內容太密，仍可能需要調整框選範圍或稍微裁掉上下空白後重跑。
