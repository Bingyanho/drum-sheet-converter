# 動態鼓譜轉換工具

這個專案可以把動態鼓譜影片轉成可列印的 JPG / PDF 樂譜頁面。

使用方式是先手動框選影片中的鼓譜區域，接著依照影片類型選擇轉換模式：

- `rows`：適合一列一列變換、或畫面局部更新的動態鼓譜。
- `scroll`：適合整張樂譜往下捲動的影片，程式會把畫面拼接成長圖，再切成 A4 頁面。

## 專案檔案

- `drum_gui.py`：圖形介面，推薦一般使用者使用。
- `drum_auto.py`：命令列工具與主要影像處理邏輯。
- `requirements.txt`：Python 套件需求。
- `run_gui.bat`：Windows 一鍵啟動 GUI。
- `.gitignore`：排除下載影片、輸出結果與快取檔。

`downloads/`、`sheet/`、`pic/` 都是執行後產生或測試用的資料夾，不需要放進 GitHub。

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
3. 選擇轉換模式：
   - `rows`：一列一列變換的動態鼓譜。
   - `scroll`：整張樂譜往下捲動的影片。
4. 按下 `Select Area and Convert`。
5. 在預覽視窗中拖曳框選鼓譜區域，按 Enter 或 Space 確認。
6. 到輸出資料夾查看產生的 JPG / PDF。

## 命令列使用

rows 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode rows --review --report-json
```

scroll 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode scroll --interval 0.35 --report-json
```

YouTube URL：

```powershell
python .\drum_auto.py "https://youtu.be/example" --name song_name --mode scroll
```

如果來源是 YouTube / web URL，下載下來的影片會在轉換成功後自動刪除，避免佔用空間。
如果想保留下載影片，可以加上：

```powershell
--keep-downloaded-video
```

## 常用參數

- `--interval`：每隔幾秒掃描一次影片。
- `--review`：輸出前逐張檢查擷取結果，僅適用 rows 模式。
- `--report-json`：輸出處理統計資料。
- `--delete-temp`：輸出後刪除中間截圖。

rows 模式參數：

- `--threshold`：畫面差異門檻。數值越低，越容易保留小變化。
- `--duplicate-threshold`：重複畫面判斷門檻。數值越低，越不容易刪掉相似但有效的頁面。

scroll 模式參數：

- `--scroll-max-shift`：每次掃描最多搜尋多少垂直位移。
- `--scroll-min-shift`：至少移動多少像素才把新內容接上去。
- `--scroll-min-score`：拼接時允許的最大對齊誤差。

## 建議設定

一般 rows 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode rows --review
```

rows 模式如果容易漏抓：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode rows --interval 0.25 --threshold 1.0 --duplicate-threshold 1.0 --review
```

scroll 模式：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode scroll --interval 0.35
```

scroll 模式如果捲動速度較快：

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode scroll --interval 0.2 --scroll-max-shift 240 --scroll-min-shift 4 --scroll-min-score 22
```

## 分享給其他人

建議只分享以下檔案：

- `drum_auto.py`
- `drum_gui.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `run_gui.bat`

不要上傳或打包以下資料夾：

- `downloads/`
- `sheet/`
- `pic/`
- `__pycache__/`

## 打包成 exe

如果要給不熟 Python 的使用者，可以用 PyInstaller 打包 GUI：

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name DrumSheetConverter drum_gui.py
```

打包完成後，執行檔會在：

```text
dist/
```
