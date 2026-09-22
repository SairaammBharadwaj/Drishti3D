const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('node:assert/strict');
// Run against a local Vite server. Playwright is a separate test dependency.
// All /api requests are fulfilled here: this script cannot submit real jobs.
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:5174';
fs.mkdirSync('/tmp/drishti-ui-check', { recursive: true });
const fixtures = [
  {id:'ready-001',name:'Neubiberg / research capture',description:'A saved scene for inspecting reconstruction evidence.',status:'done',has_video:true,has_telemetry:false},
  {id:'draft-001',name:'Riverside survey',description:'Continuous pass awaiting footage.',status:'created',has_video:false,has_telemetry:false},
  {id:'running-001',name:'Campus capture',description:'Reconstruction in progress.',status:'processing',has_video:true,has_telemetry:true},
  {id:'failed-001',name:'Low-light trial',description:'Capture needs review.',status:'failed',has_video:true,has_telemetry:false},
].map(p=>({...p,created_at:'2026-09-22T10:00:00Z',video_filename:p.has_video?'capture.mp4':null,telemetry_filename:null,intrinsics:null}));
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || undefined,headless:true,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const context=await browser.newContext({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
  const errors=[],requests=[];
  let failList=false;
  await context.route('**/api/**', async route=>{
    const req=route.request();const path=new URL(req.url()).pathname;requests.push(req.method()+' '+path);
    const json=data=>route.fulfill({json:data});
    if(path==='/api/projects' && req.method()==='GET') return failList?route.fulfill({status:503,json:{detail:'Test offline state'}}):json(fixtures);
    if(path==='/api/capabilities')return json({engines:{opencv_sfm:true,colmap:false},optional:{mesh_open3d:false,las_export:true,torch:false},ai_backends:[]});
    const project=fixtures.find(p=>path==='/api/projects/'+p.id);
    if(project)return json(project);
    if(path.endsWith('/model'))return json({frame:{lat0:0,lon0:0,alt0:0},points:[[0,0,0],[1,0,0],[0,1,0]],colors:[[100,200,100],[200,100,100],[100,100,200]],confidence:[1,1,1],provenance:[0,0,0],cameras:[],bbox:{min:[0,0,0],max:[1,1,1]}});
    if(path.endsWith('/exports'))return json({available:{}});
    if(['/questions','/measurements','/keyframes','/frame_metrics'].some(s=>path.endsWith(s)))return json([]);
    return route.fulfill({status:404,json:{detail:'Not available in UI fixture'}});
  });
  const page=await context.newPage();page.on('pageerror',e=>{errors.push(e.message); console.error('BROWSER ERROR:',e.message)});
  await page.goto(base);await page.waitForSelector('canvas');await page.waitForFunction(()=>!document.querySelector('.scene-loading'));
  await page.screenshot({path:'/tmp/drishti-ui-check/home-desktop.png'});
  await page.locator('main').evaluate(el=>el.scrollTop=950);await page.screenshot({path:'/tmp/drishti-ui-check/home-workflow.png'});await page.locator('main').evaluate(el=>el.scrollTop=0);
  await page.getByRole('button',{name:'Evidence',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Evidence',exact:true}).getAttribute('aria-pressed'),'true');
  await page.getByRole('button',{name:'Rotate scene left'}).click();
  await page.getByRole('link',{name:'Explore the workflow'}).click();
  assert(await page.locator('#how-it-works').evaluate(el=>el.getBoundingClientRect().top<150));
  await page.getByRole('link',{name:'Missions',exact:true}).click();await page.waitForSelector('.mission-card');
  assert.equal(await page.locator('.mission-card').count(),4);
  await page.screenshot({path:'/tmp/drishti-ui-check/library-desktop.png'});
  await page.getByRole('button',{name:'Ready',exact:true}).click();assert.equal(await page.locator('.mission-card').count(),1);
  await page.getByRole('button',{name:'All missions',exact:true}).click();await page.getByRole('searchbox').fill('not-present');
  assert(await page.getByText('No matching missions.').isVisible());await page.getByRole('button',{name:'Reset filters'}).click();
  await page.getByRole('link',{name:'Continue setup'}).click();await page.getByRole('heading',{name:'Upload drone video'}).waitFor();
  assert(page.url().includes('project=draft-001'));assert.equal(requests.filter(x=>x.startsWith('POST ')).length,0);
  await page.screenshot({path:'/tmp/drishti-ui-check/setup-desktop.png'});
  await page.getByRole('link',{name:'New reconstruction',exact:false}).click();await page.getByLabel('Mission name',{exact:true}).waitFor();assert.equal(await page.getByLabel('Mission name',{exact:true}).inputValue(),'');assert(!page.url().includes('project='));
  await page.goto(base+'/new');await page.getByLabel('Mission name',{exact:true}).waitFor();await page.getByLabel('Mission name',{exact:true}).fill('Browser test — not submitted');
  assert(await page.getByRole('button',{name:'Create & continue'}).isEnabled());
  await page.goto(base+'/projects/ready-001');await page.getByRole('heading',{name:'Analysis workspace'}).waitFor({timeout:10000}).catch(async e=>{console.log(await page.locator('body').innerText());throw e});
  await page.screenshot({path:'/tmp/drishti-ui-check/workspace-desktop.png'});
  for(const width of [390,768,1440]){
    await page.setViewportSize({width,height:900});await page.goto(base);await page.waitForSelector('canvas');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && document.querySelector('main').scrollWidth<=innerWidth),'homepage overflow at '+width);
    if(width===390){await page.screenshot({path:'/tmp/drishti-ui-check/home-mobile.png'});await page.getByRole('button',{name:'Menu',exact:true}).click();await page.getByRole('link',{name:'Missions',exact:true}).click();await page.waitForSelector('.mission-card');assert.equal(await page.getByRole('button',{name:'Menu',exact:true}).getAttribute('aria-expanded'),'false');await page.screenshot({path:'/tmp/drishti-ui-check/library-mobile.png'});}
  }
  await page.setViewportSize({width:390,height:900});await page.goto(base+'/new');await page.getByLabel('Mission name',{exact:true}).waitFor();await page.screenshot({path:'/tmp/drishti-ui-check/setup-mobile.png'});
  assert(await page.evaluate(()=>document.querySelector('main').scrollWidth<=innerWidth),'wizard overflow');
  await page.goto(base+'/projects/ready-001');await page.getByRole('heading',{name:'Analysis workspace'}).waitFor();assert(await page.evaluate(()=>document.querySelector('main').scrollWidth<=innerWidth),'workspace overflow');await page.screenshot({path:'/tmp/drishti-ui-check/workspace-mobile.png'});
  failList=true;await page.goto(base+'/missions');await page.getByRole('button',{name:'Try again'}).waitFor();assert(await page.getByRole('alert').isVisible());failList=false;await page.getByRole('button',{name:'Try again'}).click();await page.waitForSelector('.mission-card');
  const fallback=await context.newPage();fallback.on('pageerror',e=>errors.push(e.message));
  await fallback.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(String(type).includes('webgl'))return null;return original.call(this,type,...args)}});
  await fallback.goto(base+'/projects/ready-001');await fallback.getByText('3D rendering is unavailable in this browser.').waitFor();assert(await fallback.getByRole('link',{name:'Full report'}).isVisible());
  await fallback.close();
  assert.deepEqual(errors,[]);assert.equal(requests.filter(x=>!x.startsWith('GET ')).length,0);
  console.log(JSON.stringify({result:'PASS',checks:['homepage scene and controls','workflow anchor','mission filters and search','resume existing draft without POST','new mission form','responsive navigation','no overflow at 390/768/1440','workspace renders desktop/mobile','API failure and retry','no browser errors','no backend writes'],requests:requests.length},null,2));
  await context.close();await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
