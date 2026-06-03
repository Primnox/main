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
  await new Promise(r => setTimeout(r, 3000));
  
  // Try to click Notes
  try {
    const notesBtn = await page.locator('button[title="Notes"]');
    if (await notesBtn.count() > 0) {
        console.log('Clicking notes button...');
        await notesBtn.click();
        await new Promise(r => setTimeout(r, 2000));
    } else {
        console.log('Could not find Notes button. Trying to find any icon that looks like a note...');
        // click the 3rd sidebar button as fallback
        await page.mouse.click(20, 100);
    }
  } catch (e) {
      console.log('Failed to interact:', e);
  }

  if (errors.length === 0) {
    console.log('SUCCESS: No errors found.');
  } else {
    console.log('FAILED: Errors detected.');
  }
  await browser.close();
})();
