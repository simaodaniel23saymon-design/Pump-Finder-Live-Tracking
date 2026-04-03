// Build step for Cloudflare Pages: inject env vars into env.js
const fs = require('fs');

const env = {
  ACCESS_CODES: process.env.ACCESS_CODES || '',
  CMC_PROXY_URL: process.env.CMC_PROXY_URL || '',
  SIGNALS_API_URL: process.env.SIGNALS_API_URL || '',
  SIGNALS_API_KEY: process.env.SIGNALS_API_KEY || '',
  TELEGRAM_GROUP_URL: process.env.TELEGRAM_GROUP_URL || '',
  NEWS_RSS_URLS: process.env.NEWS_RSS_URLS || '',
  NEWS_PROXY_URL: process.env.NEWS_PROXY_URL || ''
};

const content = `window.__ENV = ${JSON.stringify(env)};`;
fs.writeFileSync('env.js', content, 'utf8');
console.log('env.js gerado');
