export async function onRequest({ env }) {
  const accessCodes = (env.ACCESS_CODES || '').trim();
  const body = [
    'window.__ENV = window.__ENV || {};',
    accessCodes ? `window.__ENV.ACCESS_CODES = ${JSON.stringify(accessCodes)};` : ''
  ].join('\n');

  return new Response(body, {
    headers: {
      'content-type': 'application/javascript; charset=utf-8',
      'cache-control': 'no-store'
    }
  });
}
