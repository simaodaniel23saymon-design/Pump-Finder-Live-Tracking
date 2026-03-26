(() => {
  window.__ENV = window.__ENV || {};

  const params = new URLSearchParams(window.location.search);
  const qpCodes = (params.get('access_codes') || params.get('access') || '').trim();

  let storedCodes = '';
  try {
    storedCodes = (localStorage.getItem('spf_access_codes') || '').trim();
  } catch {}

  if (!window.__ENV.ACCESS_CODES && qpCodes) {
    window.__ENV.ACCESS_CODES = qpCodes;
    try { localStorage.setItem('spf_access_codes', qpCodes); } catch {}
  } else if (!window.__ENV.ACCESS_CODES && storedCodes) {
    window.__ENV.ACCESS_CODES = storedCodes;
  }
})();
