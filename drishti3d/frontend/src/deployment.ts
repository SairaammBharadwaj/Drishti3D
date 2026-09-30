import { useEffect, useState } from 'react'
import { api, type Deployment } from './api'

// Asked once per page load: it cannot change while the server runs. A server
// too old to answer is a normal workspace.
let pending: Promise<Deployment> | null = null
function load() {
  return pending ??= api.deployment().catch(() => ({ read_only: false, credits: [] }))
}

/** What kind of server this is; null until known. */
export function useDeployment(): Deployment | null {
  const [d, setD] = useState<Deployment | null>(null)
  useEffect(() => { let live = true; load().then((x) => { if (live) setD(x) }); return () => { live = false } }, [])
  return d
}

/** Whether this is a read-only showcase; null until the server has said.
 *  Offer an action only when this is `false`, so a showcase never flashes a
 *  button it will refuse. */
export function useReadOnly(): boolean | null {
  return useDeployment()?.read_only ?? null
}
