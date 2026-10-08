// Supply installation and runfile labels through window.IFS_TEST_CONFIG before running.
async (page) => {
  const config = await page.evaluate(() => window.IFS_TEST_CONFIG);
  if (!config?.installation || !config?.runA || !config?.runB) {
    throw Error('Set IFS_TEST_CONFIG with installation, runA, and runB for this machine.');
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.waitForSelector('#comparison',{state:'attached'});
  const initial=await page.evaluate(()=>({tools:document.getElementById('toolsGroup').open,recent:document.getElementById('recentGroup').open,gap:document.getElementById('composer').getBoundingClientRect().top-document.getElementById('welcome').getBoundingClientRect().bottom}));
  if(initial.tools||initial.recent||initial.gap<60)throw Error('Default shell layout mismatch: '+JSON.stringify(initial));
  await page.screenshot({path:'output/companion-shell.png'});
  await page.locator('[data-view=settings]').click();
  await page.locator('#installation').fill(config.installation);
  await page.locator('#saveInstallation').click();
  await page.waitForFunction(()=>document.getElementById('settingsStatus').textContent.includes('supported runfiles'));
  await page.locator('#toolsGroup summary').click();
  await page.locator('#toolsGroup [data-view=compare]').click();
  const f=page.frameLocator('#comparison');
  await f.locator('#runA').selectOption({label:config.runA});
  await f.locator('#runB').selectOption({label:config.runB});
  await f.locator('#load').click();
  await f.locator('#variables option[value=GDP]').waitFor({state:'attached'});
  await f.locator('#variables').selectOption(['GDP','POP','AGDEM']);
  await f.locator('#compare').click();
  await page.locator('[data-view=companion]').click();
  await page.waitForFunction(async()=>{const data=await (await fetch('/api/recent')).json();return data.jobs.some(j=>j.status==='complete');},{},{timeout:120000});
  await page.locator('#recentGroup summary').click();
  await page.locator('#recent button').first().click();
  await f.locator('#results').waitFor({state:'visible'});
  await f.locator('#chart path').first().waitFor({state:'attached'});
  const result=await page.evaluate(async()=>{const doc=document.getElementById('comparison').contentDocument;const rows=Array.from(doc.querySelectorAll('#summary tr')).map(r=>r.textContent);const csv=await(await fetch(doc.getElementById('export').href)).text();return {rows,csvHeader:csv.split('\n')[0],audits:doc.querySelectorAll('#auditRows tr').length,chartPaths:doc.querySelectorAll('#chart path').length,recent:document.getElementById('recent').textContent};});
  if(result.rows.length!==3||result.rows.some(r=>r.includes('skipped'))||!result.csvHeader.includes('Variable')||result.chartPaths!==2)throw Error(JSON.stringify(result));
  await page.screenshot({path:'output/companion-comparison.png'});
  await page.reload();
  await page.waitForFunction(()=>document.getElementById('toolsGroup').open&&document.getElementById('recentGroup').open);
  await page.locator('#recent button').first().click();
  await page.frameLocator('#comparison').locator('#results').waitFor({state:'visible'});
  return {ok:true,initial,...result};
}
