/* Local browser checks with mock API responses; never refreshes production data. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.PREDICTION_TEST_URL || 'http://127.0.0.1:8015';
const origin='2026-10-10T23:00:00+06:30';
const fixture={city:'Mandalay, Myanmar',aqi_standard:'Indian CPCB AQI',calculation_version:'cpcb-2014-rolling-v1',
  forecast_origin:origin,generated_at:'2026-10-10T23:06:00+06:30',stale:false,warnings:[],
  current:{timestamp:origin,cpcb_aqi:68,stale:false,pollutants:{pm2_5:{value:8.6},pm10:{value:20},carbon_monoxide:{value:281},nitrogen_dioxide:{value:10},sulphur_dioxide:{value:5},ozone:{value:50}}},
  forecasts:Array.from({length:24},(_,i)=>({horizon:i+1,timestamp:new Date(Date.parse(origin)+(i+1)*3600000).toISOString(),predicted_cpcb_aqi:69+i,predicted_delta:i+1,category:'Satisfactory',color:'#A8C43A',precautions:'Stay informed'}))};
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    for(const [name,width,height] of [['desktop',1440,1000],['tablet',820,1180],['mobile',390,844]]) {
      for(const theme of ['dark','light']) {
        const context=await browser.newContext({viewport:{width,height}});
        const page=await context.newPage();
        await page.addInitScript(value=>localStorage.setItem('aqi-theme',value),theme);
        let posts=0,fail=false,release;
        const errors=[];page.on('pageerror',e=>errors.push(e.message));
        await page.route('**/api/**',async route=>{
          const req=route.request();
          assert.equal(req.headers().authorization,undefined);
          if(req.method()==='POST') {
            assert.ok(req.url().endsWith('/api/prediction/refresh'));
            posts++;
            await new Promise(resolve=>release=resolve);
            await route.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify(fail?{error:'Dashboard refresh authorization failed. Check the Prediction server token configuration.'}:{...fixture,manual_refresh:{status:'updated'}})});
          } else await route.fulfill({contentType:'application/json',body:JSON.stringify(req.url().includes('/latest')?{city:fixture.city,aqi_standard:fixture.aqi_standard,calculation_version:fixture.calculation_version,data:fixture.current}:fixture)});
        });
        await page.goto(base+'/prediction.html');
        await page.locator('#forecastTableBody tr').nth(23).waitFor();
        assert.equal(posts,0);
        assert.equal(await page.locator('#forecastTableBody tr').count(),24);
        assert.match(await page.locator('#forecastTableBody tr').first().innerText(),/11 Oct 2026.*12:00 AM/s);
        assert.match(await page.locator('#forecastTableBody tr').nth(23).innerText(),/11 Oct 2026.*11:00 PM/s);
        const button=page.locator('#refreshPrediction');
        const buttonBox=await button.boundingBox(),navBox=await page.locator('.page-nav').boundingBox();
        assert.ok(buttonBox.y>=navBox.y+navBox.height);
        assert.ok(buttonBox.height>=48);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
        assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('light-mode')),theme==='light');
        await button.focus();
        assert.equal(await button.evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
        await button.hover();
        await page.waitForFunction(()=>getComputedStyle(document.getElementById('refreshPrediction')).backgroundColor==='rgb(18, 86, 160)');
        const chartBefore=await page.evaluate(()=>forecastChart.id);
        await button.click();
        await page.waitForFunction(()=>document.getElementById('refreshPrediction').getAttribute('aria-busy')==='true');
        assert.equal(await button.isDisabled(),true);
        assert.equal(await page.locator('.prediction-refresh-icon').evaluate(el=>getComputedStyle(el).animationName),'prediction-spin');
        assert.equal(await page.locator('#refreshPredictionLabel').innerText(),'Updating Prediction…');
        await page.waitForFunction(()=>document.getElementById('predictionRefreshMessage').textContent.includes('Checking'));
        // The browser click handler ignores another click while pending.
        await page.evaluate(()=>document.getElementById('refreshPrediction').dispatchEvent(new MouseEvent('click')));
        while(!release)await new Promise(resolve=>setTimeout(resolve,10));
        assert.equal(posts,1);release();release=null;
        await page.waitForFunction(()=>!document.getElementById('refreshPrediction').disabled);
        assert.match(await page.locator('#predictionRefreshMessage').innerText(),/updated successfully/);
        assert.match(await page.locator('#predictionUpdate').innerText(),/11:06 PM.*Asia\/Yangon/);
        assert.equal(await page.evaluate(()=>forecastChart.id),chartBefore);
        assert.match(await page.evaluate(()=>forecastChart.data.labels[0].join(' ')),/11 Oct 2026.*12:00 AM/);
        const previousTable=await page.locator('#forecastTableBody').innerHTML();
        fail=true;await button.click();
        while(!release)await new Promise(resolve=>setTimeout(resolve,10));
        release();release=null;
        await page.waitForFunction(()=>!document.getElementById('refreshPrediction').disabled);
        assert.match(await page.locator('#predictionRefreshMessage').innerText(),/authorization failed/);
        assert.equal(await page.locator('#forecastTableBody').innerHTML(),previousTable);
        if(process.env.PREDICTION_SCREENSHOTS) {
          fs.mkdirSync(process.env.PREDICTION_SCREENSHOTS,{recursive:true});
          await page.screenshot({path:process.env.PREDICTION_SCREENSHOTS+'/'+name+'-'+theme+'.png',fullPage:true});
        }
        assert.deepEqual(errors,[]);
        await context.close();
        console.log('PASS browser:',name,theme,'24 targets, midnight, refresh/loading/failure, chart reuse, no overflow');
      }
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
