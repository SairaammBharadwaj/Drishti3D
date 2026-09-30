// Deterministic screenshots: exactly one rendered frame per encoded frame.
// Unlike CDP screencast events, capture timing cannot shorten a static take.
import {mkdir} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {connect,findViewer,sleep} from './demo_cdp.mjs'
const out=new URL('../docs/demo/final_video/narrated/captures/',import.meta.url).pathname
await mkdir(out,{recursive:true})
const c=await connect()
const chosen=process.argv.slice(2)
const wants=n=>!chosen.length||chosen.includes(n)
const hk3='288ca0888eee49f8b64446e5ffe6d6d0', hk2='a9fb1f4b3bf843a18eaf60d0f6417217', austin='051960beb15a4e1a8b851a8fa5bcc6e1'
async function waitFor(expr){for(let i=0;i<90;i++){if(await c.evaluate(expr))return;await sleep(500)}throw Error('Not ready: '+expr)}
async function nav(path,ready){await c.navigate(path);if(ready)await waitFor(ready)}
async function click(t){await c.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(t)})?.click()`);await sleep(500)}
async function still(name){await c.shot(out+name+'.png');console.log('Still '+name)}
async function movie(name,expression,seconds=10){
 const p=spawn('ffmpeg',['-y','-loglevel','error','-f','image2pipe','-vcodec','mjpeg','-framerate','30','-i','-','-an','-c:v','libx264','-threads','4','-preset','fast','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',out+name+'.mp4'],{stdio:['pipe','inherit','inherit']});
 const done=once(p,'exit');
 for(let i=0;i<seconds*30;i++){
   await c.evaluate(`(()=>{const t=${i/(seconds*30-1)};${expression}})()`);
   const {data}=await c.cdp('Page.captureScreenshot',{format:'jpeg',quality:96,fromSurface:true});
   if(!p.stdin.write(Buffer.from(data,'base64')))await once(p.stdin,'drain');
   if(i%90===0)console.log(name+' '+i+'/'+seconds*30)
 }
 p.stdin.end();const [code]=await done;if(code)throw Error('Encode failed');console.log('Finished '+name)
}
async function workspace(id){
 await nav('/projects/'+id,`!!document.querySelector('.viewer-canvas')`);
 await c.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Load all'))?.click()`);
 await waitFor(`!document.body.innerText.includes('Loading full cloud')`);
 await sleep(1500);await c.evaluate(findViewer);
 await c.evaluate(`window.demoViewer.controls.enabled=false;document.querySelectorAll('.viewer-hint').forEach(e=>e.style.color='#d7e2ef')`);
}
function orbit(scale,az=-2.1,tilt=.70){return `const v=window.demoViewer;const p=v.controls.target;const a=${az}+t*.14;const r=v.radius*${scale};v.camera.up.set(0,0,1);v.camera.position.set(p.x+r*Math.cos(a),p.y+r*Math.sin(a),p.z+r*${tilt});v.camera.lookAt(p);v.renderer.render(v.scene,v.camera);`}
if(wants('home')){await nav('/');await still('home');}
if(wants('missions')){await nav('/missions',`document.querySelectorAll('.mission-card').length>0`);await still('missions');await c.evaluate(`document.querySelector('.content').scrollTop=260`);await still('missions-lower');}
if(wants('setup')){await nav('/new',`!!document.querySelector('#mission-name')`);await still('setup');}
if(wants('austin')){await workspace(austin);await click('True color');await movie('austin-orbit',orbit(1.45,-.95,.95));}
if(wants('hk3')){await workspace(hk3);await click('True color');await movie('hk3-orbit',orbit(1.1,-2.25,.95));await click('Provenance');await movie('hk3-evidence',orbit(1.3,-2.1,1.05));}
if(wants('hk2')){await workspace(hk2);await click('True color');await movie('hk2-orbit',orbit(1.25,-2.2,.9));}
if(wants('full')){await workspace('654ba5c86999470d9623954e6785360f');await click('True color');await movie('hk3-full',orbit(1.45,-2.1,1.1));}
if(wants('report')){await nav('/projects/'+hk3+'/report',`!!document.querySelector('.report-section')`);await still('report-top');await movie('report-scroll',`const e=document.querySelector('.content');e.scrollTop=t*900`,8);await still('report-bottom');}
if(wants('results')){await nav('/projects/'+austin+'/demo',`!!document.querySelector('.demo-cta')`);await still('source');await click('Reveal 3D & metrics →');await waitFor(`!!document.querySelector('.demo-result-heading')`);await sleep(2000);await still('results');await movie('results-scroll',`document.querySelector('.content').scrollTop=t*650`,8);await still('results-lower');}
if(wants('prototype')){await nav('/prototype',`document.body.innerText.includes('3D scene ready')`);await click('Overview');await sleep(1200);await still('prototype');}
if(wants('measurement')){
 await workspace(hk3);await click('True color');await c.evaluate(`(()=>{${orbit(1.1,-2.25,.95).replace('t*.14','0')}})()`);
 await click('distance');
 // Use actual observed high-confidence vertices through the viewer's pick callback.
 await c.evaluate(`(()=>{let host=document.querySelector('.viewer-canvas').parentElement;let f=host[Object.keys(host).find(k=>k.startsWith('__reactFiber'))];while(f&&!f.memoizedProps?.onPick)f=f.return;if(!f)throw Error('No pick handler');const v=window.demoViewer;const ids=[];for(let i=0;i<v.provCodes.length;i++){if(v.provCodes[i]===0&&Math.abs(v.basePositions[i*3])<60&&Math.abs(v.basePositions[i*3+1])<60){ids.push(i);if(ids.length===200)break;}}window.demoPick=f.memoizedProps.onPick;window.demoPickPoints=[ids[0],ids[ids.length-1]].map(i=>Array.from(v.basePositions.slice(i*3,i*3+3)));window.demoPick(window.demoPickPoints[0]);})()`);
 await sleep(500);await still('measurement-first');await c.evaluate('window.demoPick(window.demoPickPoints[1])');await sleep(500);await still('measurement-picked');
 // Ask with a tolerance via the existing UI; this saves a real demo question.
 console.log(await c.evaluate(`Array.from(document.querySelectorAll('button')).map(b=>b.textContent)`));
 await click('Finish');await sleep(1500);await still('measurement-result');await movie('measurement-orbit',orbit(1.1,-2.25,.95),8);
}
if(wants('details')){
 for(const [id,name,az,tilt,scale,px,py] of [[austin,'city-detail',-.95,.95,.62,1070,602],[hk3,'island-detail',-2.25,.95,.50,862,457]]){
  await workspace(id);await click('True color');
  await c.evaluate(`(()=>{${orbit(id===austin?1.45:1.1,az,tilt).replace('t*.14','0')}})()`);
  const picked=await c.evaluate(`(()=>{const v=window.demoViewer;const b=v.renderer.domElement.getBoundingClientRect();const point=v.camera.position.clone();let best=Infinity,index=-1;for(let i=0;i<v.provCodes.length;i+=8){if(v.provCodes[i]>1)continue;point.fromArray(v.basePositions,i*3).project(v.camera);if(point.z>1)continue;const x=b.x+(point.x+1)*b.width/2,y=b.y+(1-point.y)*b.height/2;const d=(x-${px})**2+(y-${py})**2;if(d<best){best=d;index=i}}if(index<0)throw Error('No detail target');v.controls.target.fromArray(v.basePositions,index*3);return v.controls.target.toArray()})()`);
  console.log(name+' target '+picked);await movie(name,orbit(scale,az,tilt),10);
 }
}
if(wants('safety')){
 await workspace(hk3);await click('True color');
 await c.evaluate(`(()=>{${orbit(1.1,-2.25,.95).replace('t*.14','0')}})()`);
 await click('distance');
 const selected=[[-22.821512048353625,-24.751942188355642,-90.45179546553493],[-39.2658934382101,-57.34435865434259,-79.41795034562354]];
 for(const point of selected){await c.evaluate(`(()=>{let host=document.querySelector('.viewer-canvas').parentElement;let f=host[Object.keys(host).find(k=>k.startsWith('__reactFiber'))];while(f&&!f.memoizedProps?.onPick)f=f.return;f.memoizedProps.onPick(${JSON.stringify(point)});})()`);await sleep(300)}
 await click('Ask this as a question (distance, 2 points)');
 await waitFor(`!!document.querySelector('.qcard')`);await sleep(700);await still('measurement-result');
}
c.close()
