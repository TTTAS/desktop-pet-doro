document.getElementById('extension-id').textContent = chrome.runtime.id;
chrome.storage.local.get({port: 19846, token: '', enabled: false}).then(s => {
  document.getElementById('port').value = s.port;
  document.getElementById('token').value = s.token;
  document.getElementById('enabled').checked = s.enabled;
});
document.getElementById('settings').addEventListener('submit', async event => {
  event.preventDefault();
  await chrome.storage.local.set({
    port: Number(document.getElementById('port').value),
    token: document.getElementById('token').value.trim(),
    enabled: document.getElementById('enabled').checked,
  });
  document.getElementById('status').textContent = '已儲存。請確認 Doro 也已啟用分頁連線。';
});
