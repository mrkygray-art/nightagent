const puppeteer = require('puppeteer-core');
const fs = require('fs'); const path = require('path');
const DATA = fs.readFileSync(path.join(__dirname, '..', 'lab.json'), 'utf8');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage(); const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setRequestInterception(true);
  p.on('request', (r) => r.url().endsWith('/api/lab') ? r.respond({ status: 200, contentType: 'application/json', body: DATA }) : r.continue());
  await p.setViewport({ width: 1100, height: 900 });
  await p.goto('http://127.0.0.1:8765/lab', { waitUntil: 'networkidle0' });
  await p.screenshot({ path: path.join(__dirname, 'na-lab.png'), fullPage: true });
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await p.goto('http://127.0.0.1:8765/lab', { waitUntil: 'networkidle0' });
  console.log('sideways', await p.evaluate(() => document.documentElement.scrollWidth - innerWidth));
  await p.screenshot({ path: path.join(__dirname, 'na-lab-phone.png') });
  console.log('errors', errors); await b.close();
})();
