(() => {
  // Create a floating bubble that toggles an iframe with the chat UI.
  const script = document.currentScript;
  const src = script.getAttribute('data-src'); // URL to widget.html
  const base = script.getAttribute('data-base') || '';
  if (!src) {
    console.warn('widget.js: Missing data-src attribute');
    return;
  }

  const style = document.createElement('style');
  style.textContent = `
    .ragbot-bubble { position: fixed; right: 20px; bottom: 20px; width: 56px; height: 56px; border-radius: 50%; background:#111827; color:#fff; display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow:0 10px 20px rgba(0,0,0,0.2); z-index: 2147483000; }
    .ragbot-frame { position: fixed; right: 20px; bottom: 90px; width: min(360px, 90vw); height: min(540px, 85vh); border: 1px solid #e5e7eb; border-radius: 12px; box-shadow:0 20px 40px rgba(0,0,0,0.2); z-index: 2147483000; display:none; }
    .ragbot-close { position: absolute; right: 8px; top: 8px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 4px 8px; cursor:pointer; }
  `;
  document.head.appendChild(style);

  const bubble = document.createElement('div');
  bubble.className = 'ragbot-bubble';
  bubble.title = 'Chat';
  bubble.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M7 8h10M7 12h6M20 12c0 4.418-4.03 8-9 8-1.11 0-2.17-.17-3.15-.48L3 21l1.5-4.2C3.59 15.4 3 13.76 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const iframe = document.createElement('iframe');
  iframe.className = 'ragbot-frame';
  const url = new URL(src, location.href);
  if (base) url.searchParams.set('base', base);
  iframe.src = url.toString();
  iframe.title = 'Chat Widget';

  bubble.addEventListener('click', () => {
    const visible = iframe.style.display === 'block';
    iframe.style.display = visible ? 'none' : 'block';
  });

  document.body.appendChild(bubble);
  document.body.appendChild(iframe);
})();

