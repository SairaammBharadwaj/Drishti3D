import { writeFile } from 'node:fs/promises'
export const sleep = ms => new Promise(r => setTimeout(r, ms))
export async function connect({width=1920,height=1080,deviceScaleFactor=1}={}) {
  const targets = await (await fetch('http://127.0.0.1:9330/json/list')).json()
  const target = targets.find(t => t.type === 'page')
  const socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(r => socket.addEventListener('open', r, {once: true}))
  let id = 0
  const pending = new Map()
  socket.addEventListener('message', ({data}) => {
    const m = JSON.parse(data)
    if (!pending.has(m.id)) return
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result)
  })
  const cdp = (method, params={}) => new Promise((resolve,reject) => {
    pending.set(++id,{resolve,reject}); socket.send(JSON.stringify({id,method,params}))
  })
  const evaluate = async expression => {
    const r = await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true})
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails))
    return r.result.value
  }
  const shot = async path => {
    const {data} = await cdp('Page.captureScreenshot',{format:'png',fromSurface:true})
    await writeFile(path,Buffer.from(data,'base64'))
  }
  await cdp('Page.enable'); await cdp('Runtime.enable')
  await cdp('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor,mobile:false})
  const navigate = async path => {
    await cdp('Page.navigate',{url:'http://127.0.0.1:5173'+path}); await sleep(4500)
  }
  return {cdp,evaluate,shot,navigate,close:()=>socket.close()}
}
export const findViewer = `(() => {
  const host = document.querySelector('.viewer-canvas')?.parentElement;
  if (!host) return null;
  let f = host[Object.keys(host).find(k=>k.startsWith('__reactFiber'))];
  while(f) { let h=f.memoizedState; while(h) { const c=h.memoizedState?.current;
    if(c?.camera && c?.controls && c?.renderer) {window.demoViewer=c; return {radius:c.radius, target:c.controls.target.toArray(), camera:c.camera.position.toArray()};}
    h=h.next; } f=f.return; }
  return null;
})()`
