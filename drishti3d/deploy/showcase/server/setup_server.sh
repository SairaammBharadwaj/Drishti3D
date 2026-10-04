#!/usr/bin/env bash
# One-time setup of a laptop running a fresh Ubuntu Server 24.04 install as the
# Drishti3D showcase host. Safe to run again: every step is idempotent.
#
#   sudo bash setup_server.sh
#
# What it does:
#   - installs updates, and turns on unattended security updates with an
#     automatic 04:00 reboot when one needs it (the container comes back by
#     itself: restart: unless-stopped);
#   - keeps the machine up with the lid shut and never lets it suspend;
#   - installs Docker (Ubuntu's own package, so it is patched with the OS) and
#     Tailscale (from Tailscale's repository, for Funnel);
#   - enables the firewall with only SSH open. The public site is published by
#     Tailscale Funnel over an outbound connection, so no port is opened on the
#     router and nothing but SSH listens on the network. The container is bound
#     to 127.0.0.1 (compose.yaml), which Docker's own firewall rules would
#     otherwise bypass.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
ADMIN=${SUDO_USER:?run with sudo from your own account, not as root}

echo "== updates"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades ca-certificates curl
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52drishti-reboot <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF

echo "== stay awake with the lid shut"
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/50-drishti-server.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

echo "== wi-fi power saving off"
# Laptop Wi-Fi power saving put 200-600 ms on every LAN round trip on the first
# server (2026-09-29, Realtek RTL8822CE, rtw88 driver), which makes an image
# transfer crawl. A udev rule alone did not hold: the driver turns power saving
# back on when it associates. So: the rtw88 deep power-save state is disabled
# at module load (takes effect after a reboot), and a service turns power
# saving off once the Wi-Fi is up, on every boot.
DEBIAN_FRONTEND=noninteractive apt-get install -y iw
rm -f /etc/udev/rules.d/70-wifi-powersave-off.rules
cat > /etc/modprobe.d/rtw88-no-deep-power-save.conf <<'EOF'
# Harmless on machines without a Realtek rtw88 card.
options rtw88_core disable_lps_deep=y
options rtw88_pci disable_aspm=y
EOF
cat > /etc/systemd/system/wifi-power-save-off.service <<'EOF'
[Unit]
Description=Keep Wi-Fi power saving off (server)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for d in /sys/class/net/wl*; do [ -e "$d" ] && /usr/sbin/iw dev "$(basename "$d")" set power_save off; done; true'

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now wifi-power-save-off.service

echo "== docker"
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker "$ADMIN"

echo "== tailscale"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled
# Lets the admin account run `tailscale up`, `serve` and `funnel` without sudo,
# so the public address can be managed over plain SSH. The daemon takes a
# moment to answer after starting; setting it too early failed silently once.
for _ in $(seq 30); do tailscale status >/dev/null 2>&1 && break
  tailscale status 2>&1 | grep -q "Logged out" && break; sleep 1; done
tailscale set --operator="$ADMIN"

echo "== firewall: SSH only"
ufw allow OpenSSH
ufw --force enable

echo
echo "Done. Reboot once so the lid setting applies: sudo reboot"
echo "Then log in to Tailscale: sudo tailscale up"
