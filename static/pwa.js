/* Registers the service worker and tells the learner when they are offline. */
(() => {
  'use strict';

  const secure = location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname);
  if ('serviceWorker' in navigator && secure) {
    window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => { /* optional */ }); });
  }

  let banner = null;
  const show = (offline) => {
    if (offline && !banner) {
      banner = document.createElement('div');
      banner.className = 'offline-banner';
      banner.setAttribute('role', 'status');
      banner.textContent = 'You are offline. Practice needs a connection to the server; your saved progress is safe.';
      document.body.appendChild(banner);
    } else if (!offline && banner) {
      banner.remove();
      banner = null;
    }
  };
  window.addEventListener('offline', () => show(true));
  window.addEventListener('online', () => show(false));
  if (navigator.onLine === false) show(true);
})();
