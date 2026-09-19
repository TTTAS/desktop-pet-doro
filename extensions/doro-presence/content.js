/* Read only: never fill, click, focus or change the document. */
(() => {
  function snapshot() {
    if (document.visibilityState !== 'visible' || !document.hasFocus()) return null;
    const excluded = 'input,textarea,select,option,[contenteditable],script,style,noscript,[hidden],[aria-hidden="true"]';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const chunks = [];
    let size = 0;
    while (walker.nextNode() && size < 6000) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || parent.closest(excluded) || !parent.getClientRects().length) continue;
      const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility !== 'visible') continue;
      const text = node.textContent.replace(/\s+/g, ' ').trim();
      if (text) { chunks.push(text); size += text.length + 1; }
    }
    return {url: location.href, title: document.title, text: chunks.join('\n').slice(0, 6000), visible: true, focused: true};
  }
  chrome.runtime.onMessage.addListener((message, _sender, reply) => {
    if (message.type === 'snapshot') reply(snapshot());
  });
  // Wait for the DOM to go quiet before telling the app, so a page that is
  // still loading or being scrolled doesn't fire a burst of reactions. Still
  // fire at most every MAX_WAIT_MS while it keeps changing (e.g. a live clock),
  // so a never-quiet page isn't ignored forever.
  const SETTLE_MS = 1000;
  const MAX_WAIT_MS = 4000;
  let settleTimer = null;
  let firstChange = 0;
  function changed() {
    if (document.visibilityState !== 'visible') return;
    const now = Date.now();
    if (!firstChange) firstChange = now;
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      firstChange = 0;
      chrome.runtime.sendMessage({type: 'page_changed'}).catch(() => {});
    }, Math.min(SETTLE_MS, Math.max(0, MAX_WAIT_MS - (now - firstChange))));
  }
  new MutationObserver(changed).observe(document.documentElement, {
    // Visibility and editable state may change without changing any text node.
    subtree: true, childList: true, characterData: true, attributes: true,
  });
  document.addEventListener('visibilitychange', changed);
  window.addEventListener('focus', changed);
  window.addEventListener('pageshow', changed);
  changed();
})();
