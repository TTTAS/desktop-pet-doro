# 用聊天紀錄練 Doro 的 LoRA

Doro 已經透過 OpenAI 相容 API 接 LLM（聊天設定裡的 server URL／model）。
這份文件說明：怎麼把平常跟 Doro 的對話累積成訓練資料，練一個專屬 LoRA，再接回 Doro。

```
聊天 ──► ~/.doro/chat_log.sqlite3 ──► scripts/export_lora_dataset.py ──► data/doro_lora/
                                                                         │
Doro 聊天設定 ◄── Ollama / LM Studio / vLLM ◄── 合併或掛載 LoRA ◄── LLaMA-Factory / Unsloth
```

## 1. 累積對話

- 每次聊天成功，`ChatController` 會把「你說的話＋Doro 的完整結構化回覆」寫進
  `~/.doro/chat_log.sqlite3`（`doro_app/core/chat/chat_log.py`）。
- 只存在本機，不會上傳。環境變數 `DORO_CHAT_LOG` 可改路徑。
- 不想記錄：QSettings 的 `chat/training_log_enabled` 設為 `false`。
- app 每次啟動或清除聊天歷史都算新的一段對話（`session_id`），匯出時同一段會拼成多輪。
- Doro 自己開口（陪伴自動發話）標 `is_auto=1`；讀網頁後的回答標 `kind='web_answer'`；預設都不匯出。

**挑掉不好的回覆**：用任何 SQLite 工具（例如 [DB Browser for SQLite](https://sqlitebrowser.org/)）
把該列 `excluded` 改成 `1`，匯出就會跳過。也可以直接編輯匯出的 JSON。

資料量參考：想讓語氣明顯變成「你的 Doro」，至少累積幾百組問答；1000 組以上效果比較穩。
回覆品質比數量重要，練之前花點時間刪掉怪回覆。

## 2. 匯出訓練資料

在 Doro 的 venv 裡：

```bash
python scripts/export_lora_dataset.py --stats
```

```bash
python scripts/export_lora_dataset.py --out data/doro_lora
```

輸出 `data/doro_lora/doro_chat.json`（ShareGPT 格式）和 LLaMA-Factory 用的 `dataset_info.json`。
`data/` 已在 `.gitignore`，私人對話不會被 commit。

| 參數 | 說明 |
| --- | --- |
| `--target json`（預設） | assistant 內容是完整 JSON 回覆（含 `state`、`line`、`move`…）。練出來的模型照樣能驅動 Doro 的動作，最適合接回 Doro。 |
| `--target line` | 只留台詞。純練語氣／口頭禪，但接回 Doro 時要靠 system prompt 的格式說明才會輸出 JSON。 |
| `--system persona`（預設） | system 用你的人設文字。 |
| `--system full` | 用當下實際送出的完整 system prompt（含狀態清單與格式說明），每輪各自一筆；最貼近推論時的輸入，但檔案大很多。 |
| `--system none` | 不放 system。 |
| `--max-turns 8` | 每筆最多幾輪對話。 |
| `--include-auto` / `--include-web` | 也匯出自動發話／網頁回答。 |

## 3. 訓練 LoRA

需要 NVIDIA GPU。7B～8B 模型用 QLoRA（4-bit）大約 10–12GB VRAM 夠；沒有 GPU 可用 Google Colab／雲端 GPU。
基底模型建議挑中文好、有 Instruct 版的，例如 Qwen 系列 7B Instruct；**練跟推論要用同一個基底**。

### 方案 A：LLaMA-Factory

另開一個環境安裝 [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory)（不要裝進 Doro 的 venv）。
把 `data/doro_lora/` 整個資料夾指給它，建立 `doro_lora.yaml`：

```yaml
### model
model_name_or_path: Qwen/Qwen2.5-7B-Instruct
quantization_bit: 4            # QLoRA；VRAM 夠可拿掉

### method
stage: sft
do_train: true
finetuning_type: lora
lora_target: all
lora_rank: 16
lora_alpha: 32

### dataset
dataset: doro_chat
dataset_dir: /path/to/doro-exp-/data/doro_lora
template: qwen                 # 要對應基底模型
cutoff_len: 2048

### output
output_dir: saves/doro-lora
logging_steps: 10
save_steps: 200

### train
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
learning_rate: 1.0e-4
num_train_epochs: 3
lr_scheduler_type: cosine
warmup_ratio: 0.1
bf16: true
```

```bash
llamafactory-cli train doro_lora.yaml
```

資料少（幾百組）時 epoch 3 左右即可；回覆開始逐字背訓練資料就是練過頭，減少 epoch 或調低學習率。
也可以用 `llamafactory-cli webui` 用介面操作同樣的設定。

### 方案 B：Unsloth

[Unsloth](https://github.com/unslothai/unsloth) 的 notebook 速度快、省 VRAM，適合 Colab。
`doro_chat.json` 是標準 ShareGPT 格式（`conversations` 裡 `from`／`value`，另有 `system` 欄位），
照它的 ShareGPT 範例讀進來、套基底模型的 chat template 即可。訓練完可直接用它的 `save_pretrained_gguf` 匯出 GGUF。

## 4. 接回 Doro

Doro 只需要一個 OpenAI 相容的 `/v1/chat/completions` 端點，在聊天設定裡改 server URL 和 model 就能換成你的 LoRA。

**Ollama / LM Studio（Windows 最簡單）**：先把 LoRA 合併進基底模型，轉成 GGUF。

```bash
llamafactory-cli export --model_name_or_path Qwen/Qwen2.5-7B-Instruct --adapter_name_or_path saves/doro-lora --template qwen --finetuning_type lora --export_dir models/doro-merged
```

再用 llama.cpp 的 `convert_hf_to_gguf.py` 轉 GGUF（可再量化成 Q4_K_M），
Ollama 用 `Modelfile` 寫 `FROM ./doro.gguf` 後 `ollama create doro -f Modelfile`。
Doro 聊天設定：server URL `http://localhost:11434`、endpoint `/v1/chat/completions`、model `doro`。
LM Studio 則直接載入 GGUF、開 Local Server（預設 `http://localhost:1234`）。

**vLLM（Linux，有 GPU）**：不用合併，直接掛 LoRA：

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --enable-lora --lora-modules doro=saves/doro-lora
```

Doro 的 model 填 `doro`。

結構化回覆模式建議先用 `auto`；小模型若不支援 JSON schema，Doro 會自動改用文字模式並在格式錯誤時重問（ADR 0005）。

## 5. 循環

聊天 → 偶爾清掉壞回覆 → 匯出 → 重練 → 換模型。
每次重練都用**全部**累積的資料從基底模型重新練，比在舊 LoRA 上疊練穩定。

## 之後可以加的

- **長期記憶**（Mem0 之類）：LoRA 學的是語氣和個性，不適合記「你昨天說了什麼」。
  記憶應該另外做檢索，再塞進 system prompt；`ChatController._compose_system_prompt` 的 provider 是自然的接點。
- **GUI 一鍵匯出／訓練**：訓練要另一套 GPU 環境且很久，建議 GUI 只做「匯出訓練資料」，訓練在外部跑。
