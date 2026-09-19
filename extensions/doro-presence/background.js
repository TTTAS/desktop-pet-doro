let socket = null;
let heartbeat = null;
let reconnect = null;
let sequence = 0;
let lastSent = '';
let settings = {};
let retryMs = 1000;

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}
function clearPage() {
  sequence += 1;
  lastSent = '';
  send({type: 'clear'});
}
async function collect() {
  const mine = ++sequence;
  if (!settings.enabled || socket?.readyState !== WebSocket.OPEN) return;
  try {
    const win = await chrome.windows.getLastFocused({windowTypes: ['normal']});
    if (!win.focused) { if (mine === sequence) clearPage(); return; }
    const [tab] = await chrome.tabs.query({active: true, windowId: win.id});
    if (!tab || tab.incognito || !/^https?:\/\//.test(tab.url || '')) {
      if (mine === sequence) clearPage();
      return;
    }
    const page = await chrome.tabs.sendMessage(tab.id, {type: 'snapshot'});
    const checkWindow = await chrome.windows.get(win.id);
    const checkTab = await chrome.tabs.get(tab.id);
    if (mine !== sequence) return;
    if (!page?.focused || !page.visible || !checkWindow.focused || !checkTab.active || page.url !== checkTab.url) {
      clearPage(); return;
    }
    const message = JSON.stringify({...page, type: 'page', tab_id: tab.id});
    if (message !== lastSent) {
      lastSent = message;
      socket.send(message);
    }
  } catch {
    if (mine === sequence) clearPage(); // restricted page or not injected yet
  }
}
function scheduleReconnect() {
  clearTimeout(reconnect);
  if (!settings.enabled) return;
  reconnect = setTimeout(connect, retryMs);
  retryMs = Math.min(retryMs * 2, 60000); // transport recovery, not a speech cooldown
}
function connect() {
  if (!settings.enabled || !settings.token || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  if (!Number.isInteger(settings.port) || settings.port < 1024 || settings.port > 65535) return;
  const ws = new WebSocket(`ws://127.0.0.1:${settings.port}/presence`, ['doro-v1', `auth.${settings.token}`]);
  socket = ws;
  ws.onopen = () => {
    if (socket !== ws) { ws.close(); return; }
    retryMs = 1000;
    lastSent = '';
    chrome.action.setBadgeText({text: 'ON'});
    collect();
    clearInterval(heartbeat);
    heartbeat = setInterval(() => send({type: 'ping'}), 20000);
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    socket = null;
    clearInterval(heartbeat);
    sequence += 1;
    chrome.action.setBadgeText({text: settings.enabled ? '!' : ''});
    scheduleReconnect();
  };
  ws.onerror = () => ws.close();
  // Server messages are only liveness replies. No command execution surface.
  ws.onmessage = () => {};
}
async function configure() {
  settings = await chrome.storage.local.get({enabled: false, port: 19846, token: ''});
  clearTimeout(reconnect);
  clearInterval(heartbeat);
  clearPage();
  const old = socket;
  socket = null;
  old?.close();
  chrome.action.setBadgeText({text: ''});
  connect();
}
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
chrome.storage.onChanged.addListener((_changes, area) => { if (area === 'local') configure(); });
chrome.tabs.onActivated.addListener(() => { clearPage(); collect(); });
chrome.tabs.onRemoved.addListener(() => { clearPage(); collect(); });
chrome.tabs.onUpdated.addListener((_id, change, tab) => {
  if (!tab.active) return;
  if (change.url) clearPage();                 // navigation: drop the old page now
  if (change.status === 'complete') collect(); // only read once the page finished loading
});
chrome.windows.onFocusChanged.addListener(() => { clearPage(); collect(); });
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type === 'page_changed' && sender.tab?.active) collect();
});
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'reconnect') connect(); });
chrome.alarms.create('reconnect', {periodInMinutes: 0.5});
configure();
