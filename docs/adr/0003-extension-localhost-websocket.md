# ADR 0003：擴充與本機 WebSocket 配對

- 狀態：採用
- 日期：2026-09-10

## 背景

需要從一般瀏覽器只讀分享目前分頁，且不將 Doro 的 Playwright 設定檔與個人瀏覽器混用。

## 決策

- App 是 server，擴充 service worker 是 client；只綁定 `127.0.0.1`，預設埠 `19846`，可在 UI 改成 1024～65535。
- App 產生隨機 32-byte 配對碼；使用者將擴充 ID 填入 App，再把配對碼與埠號填入擴充。兩端預設停用。
- `/presence` 握手同時驗證精確 `Origin: chrome-extension://<id>` 與 token。token 透過 `Sec-WebSocket-Protocol: auth.<token>` 傳遞，不放在 URL。
- 協定選擇 `doro-v1`；錯 token、錯／缺 Origin、錯路徑回 HTTP 403。只接 JSON 文字，最大 64KiB，不提供遠端操作指令。
- `page` 包含 tab_id、url、title、text、visible、focused；`clear` 使目前頁失效；`ping/pong` 保活。文字最多 6000 字元。
- 每 20 秒交換心跳；service worker 斷線以退避重連，alarm 在 worker 被回收後重新喚醒。45 秒沒有有效連線訊息即不提供目前頁。
- 僅分享聚焦正常視窗的 active 分頁；擷取前後再次核對焦點與 URL，用序號丟棄過時擷取。
- 密碼、輸入框、textarea、contenteditable、隱藏文字不在分享內容中；不支援無痕模式。

## 結果與限制

配對資料保存在作業系統使用者的 AppData 與 extension storage.local；不是加密保險箱，不能防止已可讀取同一 OS 帳號檔案的程式。
一般頁面正文仍可能有私人資訊，UI 明示資料會交给目前聊天模型；兩端均能停用分享。
擴充載入／更新後，已存在的網頁可能需要重新整理才有 content script。

## 參考

- [Chrome service worker WebSocket 保活](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets)
- [websockets threading server API](https://websockets.readthedocs.io/en/stable/reference/sync/server.html)
