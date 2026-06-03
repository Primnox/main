const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('PAGE ERROR:', msg.text());
      errors.push(msg.text());
    }
  });
  page.on('pageerror', err => {
    console.log('UNCAUGHT EXCEPTION:', err.message);
    errors.push(err.message);
  });
  console.log('Navigating to http://localhost:5173...');
  await page.goto('http://localhost:5173');
  await new Promise(r => setTimeout(r, 2000));
  if (errors.length === 0) {
    console.log('SUCCESS: No errors found. The app is not blanking out!');
  } else {
    console.log('FAILED: Errors detected.');
  }
  await browser.close();
})();
