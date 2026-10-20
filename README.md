# Doro — 桌面寵物

住在桌面上的 Doro。會走動、換姿勢、被摸會有反應，也能接 LLM 跟你聊天。以 PySide6 製作。

![Doro](doro_app/res/state/idle.gif)

## 功能

- **聊天**：連接任何 OpenAI 相容的 API（例如 LM Studio），啟動後畫面上就有輸入列可以直接打字。
- **自主陪伴**：沒事時會自己散步、換姿勢、說話；可切換「安靜陪伴」，並設定她休息的位置與姿勢。
- **自訂動畫**：點擊、拖曳、移動、轉場都能換成自己的 GIF／APNG／WebP，每種可放多張隨機播放。
- **素材工廠**：把影片或網路上的動圖去背、統一尺寸，直接匯入成 Doro 的姿勢。
- **分頁陪伴**（選用）：搭配 Chromium 擴充，讓 Doro 看到你正在瀏覽的分頁並做出反應。

所有設定都在 Doro 身上按右鍵的選單裡。

## 安裝與執行

需要 Python 3.10 以上。

**Windows**：雙擊 `run_doro.bat`。第一次會自動建立虛擬環境並安裝全部功能，需要幾分鐘。

**其他平台／手動安裝**：

```bash
git clone https://github.com/TTTAS/doro-exp-.git
cd doro-exp-
pip install -e .            # 基本功能
pip install -e ".[factory]" # 選用：素材工廠
pip install -e ".[web]"     # 選用：上網與分頁陪伴
python doro.py
```

| 參數 | 說明 |
|------|------|
| `--not-topmost` | 不要讓視窗永遠置頂 |
| `--test-chat [訊息]` | 送一則測試聊天後結束 |

## 設定聊天

在 Doro 身上按右鍵 → 與 Doro 說話，展開聊天紀錄後即可填入伺服器網址與模型。本機跑 LM Studio 的話，預設是 `http://127.0.0.1:1234`。

API 金鑰只存在本機的使用者設定，不會寫進專案資料夾。

## 素材工廠

右鍵 →「素材工廠（影片去背）…」。支援 AI 去背（需安裝 `.[factory-ai]`，第一次會下載模型）或顏色去背，所有處理都在本機完成。也可以用命令列：

```bash
python -m doro_app.core.gif_factory input.mp4 output.webp --size 200
python -m doro_app.core.gif_factory a.gif b.gif --out-dir output --doro --no-matting
```

執行 `python -m doro_app.core.gif_factory --help` 可看所有參數。

## 更多文件

- [分頁陪伴設定](docs/web-presence-setup.md)
- [懸浮聊天窗設計](docs/floating-chat-plan.md)
- [陪伴行為設計](docs/companion-liveliness-plan.md)
- 開發者：[AGENTS.md](AGENTS.md)、[程式碼地圖](docs/REPO_MAP.md)

## 測試

```bash
pip install -e ".[test]"
pytest
```
