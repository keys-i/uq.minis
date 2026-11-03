#!/bin/sh
set -eu

enabled=/etc/minis/remote-mtls.enabled
root=/etc/minis/mtls
current=$root/current
roots=$root/root_ca.crt

[ -e "$enabled" ] || exit 0
previous=$(readlink "$current")
case "$previous" in releases/*) ;; *) exit 1 ;; esac
version=${previous#releases/}
case "$version" in ''|*[!A-Za-z0-9._-]*) exit 1 ;; esac
certificate=$current/server.crt
key=$current/server.key
test -s "$certificate"
test -s "$key"
test -s "$roots"
command -v step >/dev/null
command -v caddy >/dev/null
command -v openssl >/dev/null

expiry=over-14d
if step certificate needs-renewal "$certificate" --expires-in 336h; then
    expiry=under-14d
fi
if step certificate needs-renewal "$certificate" --expires-in 168h; then
    expiry=under-7d
fi
if step certificate needs-renewal "$certificate" --expires-in 72h; then
    expiry=under-3d
fi
printf 'minis_mtls_expiry_status=%s\n' "$expiry"
case "$expiry" in under-7d|under-3d) ;; *) exit 0 ;; esac

staging=$(mktemp -d "$root/.renew.XXXXXX")
next=$root/.current.$$
cleanup() {
    [ -z "$staging" ] || rm -rf -- "$staging"
    rm -f -- "$next"
}
trap cleanup 0
trap 'exit 1' 1 2 15
install -o root -g minis-edge -m 0640 "$certificate" "$staging/server.crt"
install -o root -g minis-edge -m 0640 "$key" "$staging/server.key"
step ca renew "$staging/server.crt" "$staging/server.key" --force
openssl verify -CAfile "$roots" "$staging/server.crt"
certificate_public=$(openssl x509 -in "$staging/server.crt" -pubkey -noout)
key_public=$(openssl pkey -in "$staging/server.key" -pubout)
[ "$certificate_public" = "$key_public" ]
if step certificate needs-renewal "$staging/server.crt" --expires-in 168h; then
    printf 'Renewed certificate has less than seven days remaining\n' >&2
    exit 1
fi

install -d -o root -g minis-edge -m 0750 "$root/releases"
chmod 0750 "$staging"
chown root:minis-edge "$staging"
release=$(date -u +%Y%m%dT%H%M%SZ)-$$
mv "$staging" "$root/releases/$release"
staging=
ln -s "releases/$release" "$next"
mv -Tf "$next" "$current"
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile &&
    systemctl reload caddy.service; then
    trap - 0 1 2 15
    printf 'minis_mtls_expiry_status=renewed-over-7d\n'
    exit 0
fi

ln -s "$previous" "$next"
mv -Tf "$next" "$current"
systemctl reload caddy.service || true
printf 'Certificate activation failed; previous identity restored\n' >&2
exit 1
