# Showcase server on a spare laptop

The read-only showcase runs on an old laptop at home. Tailscale Funnel gives it
a public address, `https://<hostname>.<tailnet>.ts.net`. It needs no domain
and no router port-forwarding, and the address stays the same across
restarts. Free on Tailscale's Personal plan; Funnel bandwidth is capped by
Tailscale at a level it does not publish.

Chosen on 2026-09-29 because Hugging Face Docker Spaces need a paid plan. The
image is the same one `deploy/showcase/Dockerfile` builds for any Docker host.

**Funnel alone was too slow.** It measured ~200 KB/s per stream (~385 KB/s
over four), so DJI_1001's full cloud (72 MB) took minutes. `compose.yaml`
therefore also runs a free Cloudflare quick tunnel, which measured 2.6 MB/s from
this laptop. The ts.net address stays the one to give out; the app forwards
page visits from it to the quick tunnel's current, randomly named address
(`backend/app/tunnel.py`). That address changes whenever the tunnel restarts.
If the tunnel is down, the site is served over Funnel instead, slower but
working. A domain on a Cloudflare named tunnel would give one fast, permanent
address without the forwarding step.

Measured end to end after the change: DJI_1001's workspace showed all 4.5 M
points 7.4 s after opening the ts.net address, in a fresh browser.

## 1. Install Ubuntu Server (at the laptop, once)

Uses Ubuntu Server 24.04.5 LTS (`ubuntu-24.04.5-live-server-amd64.iso`, SHA-256
`97f3d7ff…0fae0fd8` from releases.ubuntu.com). **The install erases the laptop.**

Write the ISO to a USB stick (4 GB or larger). On the workstation, plug it in,
find it with `lsblk` (a removable disk, `RM 1`, the size of the stick), then:

    sudo dd if=~/Downloads/ubuntu-24.04.5-live-server-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync

Boot the laptop from the stick (usually F12, F2, F10 or Esc at power-on). In
the installer:

| Screen | Choose |
|---|---|
| Type of install | **Ubuntu Server** (not minimized) |
| Network | Ethernet if you can; Wi-Fi works too |
| Storage | **Use an entire disk**, the laptop's disk; LVM default is fine |
| Profile | server name **`drishti3d`** (it becomes the start of the public address), your username and a password |
| Ubuntu Pro | Skip |
| SSH | **Install OpenSSH server** ✔ |
| Featured snaps | **None**. Docker comes from `setup_server.sh`, not the snap |

Reboot, remove the stick, log in at the laptop and note its address:
`hostname -I` (the first number).

## 2. Set it up (from the workstation)

    ssh-copy-id <user>@<address>                 # once, so later steps need no password
    scp deploy/showcase/server/setup_server.sh <user>@<address>:
    ssh -t <user>@<address> 'sudo bash setup_server.sh && sudo reboot'

After the reboot, log it into Tailscale and publish the site:

    ssh -t <user>@<address> 'sudo tailscale up --operator=<user>'   # open the printed link, sign in
    ssh <user>@<address> 'tailscale funnel --bg 7860'                # the first time, it prints a link to allow Funnel

`--operator` lets your account run `tailscale` without sudo from then on. It
has to be given at login: set while logged out, it was lost on the next restart.

The second command prints the public address.

## 3. Deploy (from the workstation, whenever the showcase changes)

Build the image (from `drishti3d/`), then ship it:

    .venv/bin/python scripts/export_showcase.py --out data/showcase --replace
    .venv/bin/python scripts/build_space.py --bundle data/showcase --out data/space --replace
    docker build -t drishti3d-showcase data/space
    deploy/showcase/server/deploy.sh <user>@<address>

## Running it

- The container restarts after a crash or reboot (`restart: unless-stopped`).
  Security updates install themselves, with a reboot at 04:00 when needed.
- Keep the laptop on mains power with the lid shut; it will not sleep.
- Logs: `ssh <user>@<address> docker logs --tail 50 drishti3d-showcase`
- Take the site offline: `ssh -t <user>@<address> 'sudo tailscale funnel reset'`
- If the laptop's address changes, reserve it in the router's DHCP settings,
  or SSH to it by its Tailscale name instead.
