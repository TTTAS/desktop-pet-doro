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
  let scheduled = false;
  function changed() {
    if (document.visibilityState !== 'visible' || scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      chrome.runtime.sendMessage({type: 'page_changed'}).catch(() => {});
    });
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
