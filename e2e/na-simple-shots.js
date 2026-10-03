const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 900 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => localStorage.clear());
  await p.reload({ waitUntil: 'networkidle0' });
  await p.screenshot({ path: path.join(__dirname, 'simple-desk.png') });
  await p.click('#options summary');
  await new Promise((r) => setTimeout(r, 300));
  await (await p.$('.console')).screenshot({ path: path.join(__dirname, 'simple-options.png') });
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.screenshot({ path: path.join(__dirname, 'simple-phone.png') });
  await b.close();
})();
