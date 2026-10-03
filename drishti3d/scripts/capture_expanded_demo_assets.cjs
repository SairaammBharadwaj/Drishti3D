// Lossless native-UHD browser captures of local repository views.
const {chromium}=require('/tmp/pramaan-review-browser/node_modules/playwright-core');
const fs=require('node:fs/promises');
const path=require('node:path');
const out=path.resolve(__dirname,'../docs/demo/final_video/expanded_2026_10_02');
(async()=>{
 const browser=await chromium.launch({executablePath:'/home/naveen/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',headless:true,args:['--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:2});
 const checks=[];
 for(const name of ['code-architecture','code-questions','code-refinement','code-refinement-result','code-tests','validation','brand-overlay']){
  await page.goto('file://'+path.join(out,'assets',name+'.html'));
  await page.evaluate(()=>document.fonts.ready);
  const errors=await page.evaluate(()=>Array.from(document.querySelectorAll('.content')).filter(e=>e.getBoundingClientRect().right>innerWidth-20).map(e=>e.textContent));
  if(errors.length)throw Error(name+' overflows: '+JSON.stringify(errors));
  await page.screenshot({path:path.join(out,'assets',name+'.png'),omitBackground:name==='brand-overlay'});
  checks.push({name,width:3840,height:2160,overflow:errors});
  if(name==='validation'){
   await page.evaluate(()=>{document.body.style.zoom='1.22';document.querySelector('table').scrollIntoView({block:'start'});});
   await page.screenshot({path:path.join(out,'assets','validation-detail.png')});
   await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight-innerHeight));
   await page.screenshot({path:path.join(out,'assets','validation-scope.png')});
  }
  console.log('CAPTURED',name);
 }
 await fs.writeFile(path.join(out,'capture-checks.json'),JSON.stringify(checks,null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
