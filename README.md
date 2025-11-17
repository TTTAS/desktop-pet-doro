# Doro 桌面寵物

一個基於 PySide6 的桌面寵物應用程式。

## 安裝步驟

### 1. 克隆專案
```bash
git clone https://github.com/TTTAS/doro-exp-.git
cd doro-exp-
```

### 2. 安裝 Python 依賴
```bash
pip install -r requirements.txt
```

### 3. 運行程式
```bash
python doro.py
```

## 系統需求

- Python 3.8+
- PySide6 6.10.0

## 專案結構

```
doro/
├── doro.py              # 主程式入口
├── doro_app/            # 應用程式核心模組
│   ├── cli.py          # 命令行介面
│   ├── window.py       # 主視窗
│   ├── state_service.py    # 狀態管理服務
│   ├── state_repository.py # 狀態持久化
│   └── ...
├── res/                 # 資源文件（GIF、配置等）
└── docs/               # 開發文檔

```

## 開發文檔

詳細的架構和開發文檔請參考 [docs/README.md](./docs/README.md)

## 授權

[添加授權信息]
