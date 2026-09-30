// Native 3840 x 1920 browser capture; no JPEG or post-capture enlargement.
import {mkdir} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {connect,findViewer,sleep} from './demo_cdp.mjs'
const out=new URL('../docs/demo/final_video/quality_v2/captures/',import.meta.url).pathname
await mkdir(out,{recursive:true})
const c=await connect({width:1600,height:800,deviceScaleFactor:2.4})
const selected=process.argv.slice(2)
const wants=n=>!selected.length||selected.includes(n)
const hk3='288ca0888eee49f8b64446e5ffe6d6d0',hk2='a9fb1f4b3bf843a18eaf60d0f6417217',austin='051960beb15a4e1a8b851a8fa5bcc6e1'
async function ready(expr){for(let i=0;i<150;i++){if(await c.evaluate(expr))return;await sleep(400)}throw Error('Not ready: '+expr)}
async function nav(path,expr){await c.navigate(path);if(expr)await ready(expr);await c.evaluate('document.fonts.ready');}
async function click(text){await c.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)})?.click()`);await sleep(350)}
async function still(name){
 await c.evaluate(`(()=>{const v=window.demoViewer;if(v&&document.querySelector('.viewer-canvas'))v.renderer.render(v.scene,v.camera);})()`)
 await c.shot(out+name+'.png');console.log('STILL '+name)
}
async function movie(name,expr,seconds=10){
 const p=spawn('ffmpeg',['-y','-hide_banner','-loglevel','error','-f','image2pipe','-vcodec','png','-framerate','30','-i','-','-an','-c:v','libx264','-threads','5','-preset','fast','-crf','12','-pix_fmt','yuv444p','-movflags','+faststart',out+name+'.mp4'],{stdio:['pipe','inherit','inherit']})
 const done=once(p,'exit');const frames=seconds*30
 for(let i=0;i<frames;i++){
  await c.evaluate(`(()=>{const t=${i/(frames-1)};${expr}})()`)
  await c.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  const {data}=await c.cdp('Page.captureScreenshot',{format:'png',fromSurface:true,optimizeForSpeed:true})
  if(!p.stdin.write(Buffer.from(data,'base64')))await once(p.stdin,'drain')
  if(i%30===0)console.log(name+' '+i+'/'+frames)
 }
 p.stdin.end();const [code]=await done;if(code)throw Error('Capture encoder failed');console.log('DONE '+name)
}
async function prep(){
 await c.evaluate(findViewer)
 await c.evaluate(`(()=>{const v=window.demoViewer;if(!v)throw Error('Viewer unavailable');v.controls.enabled=false;v.renderer.setPixelRatio(2.4);v.renderer.outputColorSpace='srgb';
 // Input RGB is stored in sRGB, whereas Three's vertex colors are linear.
 // Correct the color-space interpretation, without grading the actual data.
 if(!v.demoLinear){for(const a of [v.trueColors,v.provColors])for(let i=0;i<a.length;i++){const s=a[i];a[i]=s<=.04045?s/12.92:Math.pow((s+.055)/1.055,2.4)}v.demoLinear=true;}
 v.scene.children.filter(o=>o!==v.points&&o.isPoints).forEach(o=>o.material.size=v.radius*.003);
 document.querySelectorAll('.viewer-hint').forEach(e=>e.style.color='#e8edf4');
 // Capture drives each frame explicitly. Avoid rendering millions of points
 // dozens of redundant times between lossless screenshots.
 if(!window.demoRAF){window.demoRAF=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=fn=>fn.name==='animate'?0:window.demoRAF(fn);}
 })()`)
}
async function mode(text){await click(text);await c.evaluate(`(()=>{const v=window.demoViewer;v.points.geometry.attributes.color.array.set(v.${text==='True color'?'trueColors':'provColors'});v.points.geometry.attributes.color.needsUpdate=true;})()`)}
async function workspace(id){
 await nav('/projects/'+id,`!!document.querySelector('.viewer-canvas')`)
 await c.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Load all'))?.click()`)
 await ready(`document.body.innerText.includes('FULL CLOUD')&&!document.body.innerText.includes('Loading full cloud')`)
 await sleep(900);await prep();await mode('True color')
}
function orbit(scale,az=-.95,tilt=1.05,arc=.12){return `const v=window.demoViewer,p=v.controls.target,a=${az}+${arc}*(t*t*(3-2*t)),r=v.radius*${scale};v.camera.up.set(0,0,1);v.camera.position.set(p.x+r*Math.cos(a),p.y+r*Math.sin(a),p.z+r*${tilt});v.camera.lookAt(p);v.renderer.render(v.scene,v.camera);`}
async function camera(expr){await c.evaluate(`(()=>{const t=0;${expr}})()`)}
async function pick(points){for(const point of points){await c.evaluate(`(()=>{let f=document.querySelector('.viewer-canvas').parentElement;f=f[Object.keys(f).find(k=>k.startsWith('__reactFiber'))];while(f&&!f.memoizedProps?.onPick)f=f.return;if(!f)throw Error('No pick handler');f.memoizedProps.onPick(${JSON.stringify(point)});})()`);await sleep(250)}}
if(wants('home')){await nav('/');await still('home')}
if(wants('missions')){await nav('/missions',`document.querySelectorAll('.mission-card').length>0`);await still('missions')}
if(wants('setup')){await nav('/new',`!!document.querySelector('#mission-name')`);await still('setup')}
if(wants('austin')){await workspace(austin);await movie('austin-orbit',orbit(.96,-.95,1.05))}
if(wants('hk3')){await workspace(hk3);await movie('hk3-orbit',orbit(.89,-2.25,1.12));await mode('Provenance');await movie('hk3-evidence',orbit(.98,-2.25,1.15))}
if(wants('hk2')){await workspace(hk2);await movie('hk2-orbit',orbit(.95,-2.2,1.1))}
if(wants('full')){await workspace('654ba5c86999470d9623954e6785360f');await movie('hk3-full',orbit(1.10,-2.1,1.15),18)}
if(wants('report')){await nav('/projects/'+hk3+'/report',`!!document.querySelector('.report-section')`);await still('report-top');await movie('report-scroll',`document.querySelector('.content').scrollTop=1050*(t*t*(3-2*t))`,10);await still('report-bottom')}
if(wants('results')){
 await nav('/projects/'+austin+'/demo',`!!document.querySelector('.demo-cta')`);await still('source');await click('Reveal 3D & metrics →');await ready(`!!document.querySelector('.demo-result-heading')`);await sleep(1200);
 // Load the complete cloud through the product control when available.
 await c.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Load all'))?.click()`);await sleep(1500);
 if(await c.evaluate(findViewer)){await prep();await c.evaluate(`(()=>{const v=window.demoViewer;v.points.geometry.attributes.color.array.set(v.trueColors);v.points.geometry.attributes.color.needsUpdate=true;})()`);await camera(orbit(.9,-.95,1.05))}
 await still('results');await movie('results-scroll',`document.querySelector('.content').scrollTop=630*(t*t*(3-2*t))`,10);await still('results-lower')
}
if(wants('prototype')){await nav('/prototype',`document.body.innerText.includes('3D scene ready')`);await click('Overview');await sleep(1200);await still('prototype')}
if(wants('details')){
 for(const [id,name,az,tilt,scale,u,w] of [[austin,'city-detail',-.95,1.1,.52,.65,.54],[hk3,'island-detail',-2.25,1.15,.54,.48,.54]]){
  await workspace(id);await camera(orbit(id===austin?.96:.89,az,tilt));
  console.log(await c.evaluate(`(()=>{const v=window.demoViewer,b=v.renderer.domElement.getBoundingClientRect(),p=v.camera.position.clone();let best=Infinity,index=-1;for(let i=0;i<v.provCodes.length;i+=8){if(v.provCodes[i]>1)continue;p.fromArray(v.basePositions,i*3).project(v.camera);if(p.z>1)continue;const d=((p.x+1)/2-${u})**2+((1-p.y)/2-${w})**2;if(d<best){best=d;index=i}}if(index<0)throw Error('No detail target');v.controls.target.fromArray(v.basePositions,index*3);return {target:v.controls.target.toArray()}})()`));
  await movie(name,orbit(scale,az,tilt))
 }
}
if(wants('measurement')){
 await workspace(hk3);await camera(orbit(.85,-2.25,1.12));await click('distance');
 const points=[[-22.821512048353625,-24.751942188355642,-90.45179546553493],[-39.2658934382101,-57.34435865434259,-79.41795034562354]];
 await pick(points.slice(0,1));await still('measurement-first');await pick(points.slice(1));await still('measurement-picked');
 // Inspect the existing persisted question rather than creating duplicates.
 await click('Cancel');await c.evaluate(`document.querySelector('.qcard')?.scrollIntoView({block:'center'})`);await sleep(500);await still('measurement-result')
}
c.close()
