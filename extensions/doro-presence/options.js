const status = document.getElementById('status');

// Reflect only the current share state; the pairing code is write-only so the
// secret is never shown back after it has been stored.
chrome.storage.local.get({enabled: false}).then(s => {
  document.getElementById('enabled').checked = s.enabled;
});

// doro1.<port>.<token> -- built by the Doro app's "複製配對碼" button.
const PAIRING = /^doro1\.(\d{4,5})\.([A-Za-z0-9_-]{32,128})$/;

document.getElementById('settings').addEventListener('submit', async event => {
  event.preventDefault();
  const enabled = document.getElementById('enabled').checked;
  const code = document.getElementById('code').value.trim();
  if (code) {
    const match = PAIRING.exec(code);
    if (!match) {
      status.textContent = '配對碼格式不正確，請在 Doro 按「複製配對碼」重新複製。';
      return;
    }
    const port = Number(match[1]);
    if (port < 1024 || port > 65535) {
      status.textContent = '配對碼的埠號超出範圍（1024～65535）。';
      return;
    }
    // A pasted code means "pair and share", so enable without a second click.
    document.getElementById('enabled').checked = true;
    await chrome.storage.local.set({port, token: match[2], enabled: true});
    document.getElementById('code').value = '';
    status.textContent = '已配對並開始分享。切回瀏覽器的一般分頁即可。';
    return;
  }
  // No code entered: just flip the share state (pause / resume).
  const saved = await chrome.storage.local.get({token: ''});
  if (enabled && !saved.token) {
    status.textContent = '尚未配對，請先貼上 Doro 的配對碼。';
    return;
  }
  await chrome.storage.local.set({enabled});
  status.textContent = enabled ? '已恢復分享。' : '已暫停分享。';
});
