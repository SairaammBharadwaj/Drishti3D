import { writeFile } from 'node:fs/promises'

const endpoint = 'http://127.0.0.1:9322'
const out = new URL('../docs/demo/video_capture/', import.meta.url)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const targets = await (await fetch(`${endpoint}/json/list`)).json()
const target = targets.find((item) => item.type === 'page')
if (!target) throw new Error('No Chrome page is available for capture.')

const socket = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

let sequence = 0
const pending = new Map()
socket.addEventListener('message', ({ data }) => {
  const message = JSON.parse(data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    message.error ? reject(new Error(message.error.message)) : resolve(message.result)
  }
})
const cdp = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence
  pending.set(id, { resolve, reject })
  socket.send(JSON.stringify({ id, method, params }))
})

await cdp('Emulation.setDeviceMetricsOverride', {
  width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false,
})
await cdp('Page.enable')
await cdp('Runtime.enable')

async function navigate(path) {
  await cdp('Page.navigate', { url: `http://127.0.0.1:5173${path}` })
  await sleep(4500)
}

async function evaluate(expression) {
  return cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
}

async function clickText(text) {
  await evaluate(`Array.from(document.querySelectorAll('button, a')).find((el) => el.textContent?.trim().includes(${JSON.stringify(text)}))?.click()`)
  await sleep(1200)
}

async function screenshot(name) {
  const { data } = await cdp('Page.captureScreenshot', { format: 'png', fromSurface: true })
  await writeFile(new URL(`${name}.png`, out), Buffer.from(data, 'base64'))
}

await navigate('/missions')
await screenshot('missions')

await navigate('/projects/051960beb15a4e1a8b851a8fa5bcc6e1')
await screenshot('workspace-true-colour-preview')
await clickText('Provenance')
await screenshot('workspace-provenance')

await navigate('/prototype')
await screenshot('research-prototype')

await navigate('/projects/051960beb15a4e1a8b851a8fa5bcc6e1/demo')
await screenshot('showcase')
await clickText('Reveal 3D & metrics')
await screenshot('showcase-results')

await navigate('/projects/051960beb15a4e1a8b851a8fa5bcc6e1/report')
await screenshot('evidence-report')

// Independent-validation sequence: retain these as a named Hong Kong pair in
// the edit. They must never be presented as measurements of the Austin model.
await navigate('/projects/a9fb1f4b3bf843a18eaf60d0f6417217')
await screenshot('hkisland02-single-pass')

await navigate('/projects/288ca0888eee49f8b64446e5ffe6d6d0')
await screenshot('hkisland03-single-pass')

await navigate('/projects/9bf35ab6e8fa4b7f9de20435b6e1043b')
await screenshot('hkisland02-full-window')

await navigate('/projects/654ba5c86999470d9623954e6785360f')
await screenshot('hkisland03-full-window')

socket.close()
