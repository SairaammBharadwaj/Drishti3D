/*
 * Records clean, voice-over-free product takes directly from the live app.
 * Requires Chrome started with --remote-debugging-port=9323.
 *
 * Output clips are 1920x1080 H.264 at 60 fps and are intended as source
 * footage for the timestamped final demo edit.
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'

const endpoint = 'http://127.0.0.1:9323'
const root = new URL('../docs/demo/video_capture/raw/', import.meta.url)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

await mkdir(root, { recursive: true })
const targets = await (await fetch(`${endpoint}/json/list`)).json()
const page = targets.find((target) => target.type === 'page')
if (!page) throw new Error('No Chrome page found. Start the recorder browser first.')

const socket = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

let sequence = 0
const pending = new Map()
let activeFrames = null
let writes = []
socket.addEventListener('message', ({ data }) => {
  const message = JSON.parse(data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    message.error ? reject(new Error(message.error.message)) : resolve(message.result)
    return
  }
  if (message.method !== 'Page.screencastFrame' || !activeFrames) return
  const { data: frame, sessionId } = message.params
  const index = activeFrames.count++
  writes.push(writeFile(new URL(`${activeFrames.name}-${String(index).padStart(5, '0')}.jpg`, root), Buffer.from(frame, 'base64')))
  socket.send(JSON.stringify({ id: ++sequence, method: 'Page.screencastFrameAck', params: { sessionId } }))
})
const cdp = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence
  pending.set(id, { resolve, reject })
  socket.send(JSON.stringify({ id, method, params }))
})

await cdp('Page.enable')
await cdp('Runtime.enable')
await cdp('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false })

async function navigate(path) {
  await cdp('Page.navigate', { url: `http://127.0.0.1:5173${path}` })
  await sleep(5000)
}
async function evaluate(expression) {
  await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
}
async function record(name, seconds, motion) {
  activeFrames = { name, count: 0 }
  writes = []
  await cdp('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 })
  const cleanup = motion?.()
  await sleep(seconds * 1000)
  if (cleanup) clearInterval(cleanup)
  await cdp('Page.stopScreencast')
  await sleep(500)
  await Promise.all(writes)
  const frames = activeFrames.count
  activeFrames = null
  if (frames < 2) throw new Error(`${name}: Chrome produced too few frames (${frames}).`)
  await new Promise((resolve, reject) => {
    const input = new URL(`${name}-%05d.jpg`, root).pathname
    const output = new URL(`${name}.mp4`, root).pathname
    const ffmpeg = spawn('ffmpeg', ['-y', '-hide_banner', '-loglevel', 'error', '-framerate', '30', '-i', input,
      '-vf', 'scale=1920:1080:flags=lanczos,fps=60', '-c:v', 'libx264', '-preset', 'slow', '-crf', '17',
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', output], { stdio: 'inherit' })
    ffmpeg.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`${name}: ffmpeg exited ${code}`)))
  })
  console.log(`Recorded ${name}: ${frames} frames`)
}

await navigate('/')
await record('home-hkisland03', 9, () => setInterval(() => {
  evaluate("document.querySelector('button[aria-label=\"Rotate scene right\"]')?.click()")
}, 900))

await navigate('/projects/288ca0888eee49f8b64446e5ffe6d6d0')
await evaluate("Array.from(document.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'True color')?.click()")
await record('hkisland03-true-colour', 9)
await evaluate("Array.from(document.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'Provenance')?.click()")
await record('hkisland03-provenance', 9)

await navigate('/projects/288ca0888eee49f8b64446e5ffe6d6d0/report')
await record('hkisland03-evidence-report', 8, () => setInterval(() => {
  evaluate('window.scrollBy({ top: 55, behavior: "smooth" })')
}, 750))

socket.close()
console.log(`Finished. Source clips: ${root.pathname}`)
