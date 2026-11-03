# Optional cross-host mTLS profile

This profile gives a separate Caddy peer a verified service identity for the narrow metrics route
Local cloudflared, Caddy, UQ and SOC traffic stays on Unix sockets without TLS

It is installed as inert reference material under `/usr/local/share/minis/mtls`
The normal installer does not import the Caddy site, open TCP 9443, install the systemd units or enable the timer

To evaluate it on a remote host

1. Install `step` and OpenSSL, initialise the Smallstep trust context beneath `/etc/minis/step` and issue short-lived server and client identities
2. Put the first `server.crt` and `server.key` in a single `/etc/minis/mtls/releases/<version>/` directory, put `root_ca.crt` in `/etc/minis/mtls`, then atomically link `/etc/minis/mtls/current` to that relative release path
3. Copy `remote.caddy` to `/etc/caddy/minis.d/remote.caddy`
4. Copy `caddy-remote.conf` to `/etc/systemd/system/caddy.service.d/remote.conf`
5. Copy the rotation units into `/etc/systemd/system/`, create `/etc/minis/remote-mtls.enabled`, validate Caddy and explicitly enable the timer
6. Configure the peer Caddy to present its client identity, permit TCP 9443 only between the two hosts and verify an untrusted client certificate is rejected

The leaf certificate reports 14, 7 and 3 day status, renews inside a private staging directory below seven days, verifies the trust chain and key pair, then atomically switches the current identity before reloading Caddy
Removing the marker and imported Caddy file disables renewal and the remote listener after a daemon reload and Caddy restart
