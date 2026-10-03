const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage(); const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1100, height: 900 });
  await p.goto('https://nightshift-dispatch.vercel.app/lab?v=1', { waitUntil: 'networkidle0' });
  console.log(await p.$eval('#summary', (n) => n.innerText.replace(/\n/g, ' | ')));
  console.log('cards', await p.$$eval('.test', (n) => n.length));
  await p.screenshot({ path: path.join(__dirname, 'na-lab-live.png') });
  await p.goto('https://nightshift-dispatch.vercel.app/demo?v=3', { waitUntil: 'networkidle0' });
  console.log('demo link', await p.$$eval('a[href="/lab"]', (n) => n.length));
  console.log('errors', errors); await b.close();
})();
