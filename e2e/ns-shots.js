const puppeteer = require('puppeteer-core');
const OUT = 'C:/Users/mrkyg/AppData/Local/Temp/claude/c--Users-mrkyg-projects-pictalk/601f8bfc-ec0a-4e1d-a5aa-089c57fe4dd3/scratchpad/ns/';
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  const p = await b.newPage();
  await p.setViewport({ width: 1400, height: 1000, deviceScaleFactor: 1 });
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle2' });
  await new Promise((r) => setTimeout(r, 2500));
  // Open the demo-customers list like in the reference screenshot
  await p.evaluate(() => { const d = document.querySelector('details'); if (d) d.open = true; });
  await new Promise((r) => setTimeout(r, 500));
  const info = await p.evaluate(() => ({ h: document.documentElement.scrollHeight, tickets: document.body.innerText.includes('NS-') }));
  console.log(JSON.stringify(info));
  await p.screenshot({ path: OUT + 'demo-full.png', fullPage: true });
  await p.goto('https://nightshift-dispatch.vercel.app/', { waitUntil: 'networkidle2' });
  await p.setViewport({ width: 1400, height: 700, deviceScaleFactor: 1 });
  await p.screenshot({ path: OUT + 'log.png', fullPage: true });
  await b.close();
})();
