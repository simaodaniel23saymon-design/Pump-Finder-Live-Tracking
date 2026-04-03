export async function onRequest({ env }) {
  const accessCodes = (env.ACCESS_CODES || '').trim();
  const cmcProxy = (env.CMC_PROXY_URL || '').trim();
  const signalsApi = (env.SIGNALS_API_URL || '').trim();
  const signalsKey = (env.SIGNALS_API_KEY || '').trim();
  const tgGroup = (env.TELEGRAM_GROUP_URL || '').trim();
  const newsRss = (env.NEWS_RSS_URLS || '').trim();
  const newsProxy = (env.NEWS_PROXY_URL || '').trim();
  const body = [
    'window.__ENV = window.__ENV || {};',
    accessCodes ? `window.__ENV.ACCESS_CODES = ${JSON.stringify(accessCodes)};` : '',
    cmcProxy ? `window.__ENV.CMC_PROXY_URL = ${JSON.stringify(cmcProxy)};` : '',
    signalsApi ? `window.__ENV.SIGNALS_API_URL = ${JSON.stringify(signalsApi)};` : '',
    signalsKey ? `window.__ENV.SIGNALS_API_KEY = ${JSON.stringify(signalsKey)};` : '',
    tgGroup ? `window.__ENV.TELEGRAM_GROUP_URL = ${JSON.stringify(tgGroup)};` : '',
    newsRss ? `window.__ENV.NEWS_RSS_URLS = ${JSON.stringify(newsRss)};` : '',
    newsProxy ? `window.__ENV.NEWS_PROXY_URL = ${JSON.stringify(newsProxy)};` : ''
  ].join('\n');

  return new Response(body, {
    headers: {
      'content-type': 'application/javascript; charset=utf-8',
      'cache-control': 'no-store'
    }
  });
}
