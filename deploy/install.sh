#!/bin/sh
# Install immutable code separately from the private browser workspace
set -eu
umask 022

stage=$1
revision=$2
case "$stage" in /tmp/minis.??????????) ;; *) exit 2 ;; esac
case "$revision" in ''|*[!a-f0-9]*) exit 2 ;; esac
[ "${#revision}" -eq 32 ]
[ "$(id -u)" -eq 0 ]
command -v uv >/dev/null
command -v ffmpeg >/dev/null
command -v curl >/dev/null
command -v caddy >/dev/null
command -v cloudflared >/dev/null
command -v systemd-tmpfiles >/dev/null
command -v stat >/dev/null
if [ ! -f /etc/minis/google-oauth.json ] || [ -L /etc/minis/google-oauth.json ]; then
    printf 'Provision /etc/minis/google-oauth.json as a Google Web OAuth client before deploying\n' >&2
    exit 1
fi
case "$(stat -c %a /etc/minis/google-oauth.json)" in
    400|600) ;;
    *) printf 'Set /etc/minis/google-oauth.json permissions to 0400 or 0600\n' >&2; exit 1 ;;
esac
install -d -m 755 /opt/minis/releases
exec 9>/opt/minis/deploy.lock
flock -n 9
getent passwd minis >/dev/null || useradd --system --home-dir /var/lib/minis --shell /usr/sbin/nologin minis
getent group minis-edge >/dev/null || groupadd --system minis-edge
getent group soc-minis >/dev/null || groupadd --system soc-minis
getent passwd caddy >/dev/null || useradd --system --gid minis-edge --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy
usermod -a -G minis-edge caddy
usermod -a -G soc-minis caddy
install -d -m 700 /var/lib/minis
chown minis:minis /var/lib/minis
install -d -o caddy -g minis-edge -m 700 /var/lib/caddy
release=/opt/minis/releases/$revision
mkdir "$release"
cp -R "$stage/frontend" "$release/frontend"
cp -R "$stage/mtls" "$release/mtls"
chmod 755 "$release/mtls/rotate.sh"
# Keep managed Python outside root's home so ProtectHome can remain enabled
export UV_PYTHON_INSTALL_DIR=/opt/minis/python
uv venv --managed-python --python 3.15 "$release/.venv"
uv pip sync --python "$release/.venv/bin/python" --compile-bytecode --require-hashes "$stage/requirements.txt"
uv pip install --python "$release/.venv/bin/python" --no-deps --compile-bytecode "$stage/"*.whl
install -d -m 755 /opt/minis/browsers
PLAYWRIGHT_BROWSERS_PATH=/opt/minis/browsers "$release/.venv/bin/playwright" install chromium
chmod -R a+rX /opt/minis/browsers

previous=$(readlink /opt/minis/current || true)
next=/opt/minis/.next-$revision
unit_state() {
    systemctl is-enabled "$1" 2>/dev/null || true
}
restore_unit_state() {
    unit=$1
    state=$2
    case "$state" in
        enabled) systemctl enable "$unit" >/dev/null ;;
        enabled-runtime) systemctl enable --runtime "$unit" >/dev/null ;;
        masked) systemctl mask --force "$unit" >/dev/null ;;
        masked-runtime) systemctl mask --runtime --force "$unit" >/dev/null ;;
        disabled|static|indirect|generated|transient|not-found|'')
            systemctl disable "$unit" >/dev/null 2>&1 || true
            ;;
        *) return 1 ;;
    esac
}
stop_if_active() {
    if systemctl is-active --quiet "$1"; then
        systemctl stop "$1"
    fi
}
soc_ready() {
    if ! systemctl is-active --quiet soc-minis.service; then
        return 0
    fi
    curl --silent --fail --max-time 3 --unix-socket /run/soc-minis/app.sock \
        -H "Host: uni.keysi.dev" http://localhost/health/ready >/dev/null &&
        curl --silent --fail --max-time 3 --unix-socket /run/minis-edge/caddy.sock \
            -H "Host: minis-origin.keysi.dev" http://localhost/soc/api/health/ready >/dev/null
}
minis_service_state=$(unit_state minis.service)
minis_socket_state=$(unit_state minis.socket)
caddy_state=$(unit_state caddy.service)
cloudflared_state=$(unit_state cloudflared-minis.service)
remember() {
    path=$1
    name=$2
    if [ -f "$path" ]; then
        cp "$path" "$stage/previous.$name"
    else
        : >"$stage/absent.$name"
    fi
}
restore() {
    path=$1
    name=$2
    if [ -f "$stage/previous.$name" ]; then
        install -m 644 "$stage/previous.$name" "$path"
    elif [ -f "$stage/absent.$name" ]; then
        rm -f "$path"
    fi
}
remember /etc/systemd/system/minis.service minis.service
remember /etc/systemd/system/minis.socket minis.socket
remember /etc/systemd/system/minis@.service minis@.service
remember /etc/systemd/system/minis@.socket minis@.socket
remember /etc/systemd/system/caddy.service caddy.service
remember /etc/systemd/system/cloudflared-minis.service cloudflared-minis.service
remember /etc/polkit-1/rules.d/50-minis.rules minis.rules
remember /etc/caddy/Caddyfile Caddyfile
remember /etc/cloudflared/minis.yml cloudflared.yml
remember /etc/tmpfiles.d/minis.conf minis.tmpfiles
rollback() {
    status=$?
    trap - 0 1 2 15
    set +e
    recovery_failed=0
    rm -f "$next"
    restore /etc/systemd/system/minis.service minis.service || recovery_failed=1
    restore /etc/systemd/system/minis.socket minis.socket || recovery_failed=1
    restore /etc/systemd/system/minis@.service minis@.service || recovery_failed=1
    restore /etc/systemd/system/minis@.socket minis@.socket || recovery_failed=1
    restore /etc/systemd/system/caddy.service caddy.service || recovery_failed=1
    restore /etc/systemd/system/cloudflared-minis.service cloudflared-minis.service || recovery_failed=1
    restore /etc/polkit-1/rules.d/50-minis.rules minis.rules || recovery_failed=1
    restore /etc/caddy/Caddyfile Caddyfile || recovery_failed=1
    restore /etc/cloudflared/minis.yml cloudflared.yml || recovery_failed=1
    restore /etc/tmpfiles.d/minis.conf minis.tmpfiles || recovery_failed=1
    systemctl daemon-reload || recovery_failed=1
    restore_unit_state minis.service "$minis_service_state" || recovery_failed=1
    restore_unit_state minis.socket "$minis_socket_state" || recovery_failed=1
    restore_unit_state caddy.service "$caddy_state" || recovery_failed=1
    restore_unit_state cloudflared-minis.service "$cloudflared_state" || recovery_failed=1
    if [ -n "$previous" ]; then
        ln -s "$previous" "$next" || recovery_failed=1
        mv -Tf "$next" /opt/minis/current || recovery_failed=1
        if [ -f /etc/systemd/system/minis.socket ]; then
            systemctl restart minis.socket || recovery_failed=1
        else
            stop_if_active minis.socket || recovery_failed=1
        fi
        systemctl restart minis.service || recovery_failed=1
    else
        stop_if_active minis.service || recovery_failed=1
        stop_if_active minis.socket || recovery_failed=1
        rm -f /opt/minis/current || recovery_failed=1
    fi
    if [ -f /etc/caddy/Caddyfile ]; then
        systemctl restart caddy.service || recovery_failed=1
    else
        stop_if_active caddy.service || recovery_failed=1
    fi
    if [ -f /etc/cloudflared/minis.yml ] && [ -f /etc/cloudflared/minis.json ] && [ -f /etc/cloudflared/minis.env ]; then
        systemctl restart cloudflared-minis.service || recovery_failed=1
    else
        stop_if_active cloudflared-minis.service || recovery_failed=1
    fi
    if [ "$recovery_failed" -eq 1 ]; then
        printf 'New release failed and automatic restoration was incomplete\n' >&2
    else
        printf 'New release failed; previous code restored and private state preserved\n' >&2
    fi
    exit "$status"
}
trap rollback 0
trap 'exit 1' 1 2 15
install -d -m 755 /etc/caddy /etc/caddy/minis.d /etc/cloudflared /etc/tmpfiles.d /usr/local/share/minis
install -m 644 "$stage/Caddyfile" /etc/caddy/Caddyfile
install -m 644 "$stage/cloudflared.yml" /etc/cloudflared/minis.yml
install -m 644 "$stage/minis.tmpfiles" /etc/tmpfiles.d/minis.conf
install -m 644 "$stage/caddy.service" /etc/systemd/system/caddy.service
install -m 644 "$stage/tunnel.service" /etc/systemd/system/cloudflared-minis.service
install -m 644 "$stage/minis.socket" /etc/systemd/system/minis.socket
install -m 644 "$stage/minis@.service" /etc/systemd/system/minis@.service
install -m 644 "$stage/minis@.socket" /etc/systemd/system/minis@.socket
install -m 644 "$stage/minis.rules" /etc/polkit-1/rules.d/50-minis.rules
install -m 644 "$stage/minis.service" /etc/systemd/system/minis.service
caddy validate --config "$stage/Caddyfile" --adapter caddyfile
systemd-tmpfiles --create /etc/tmpfiles.d/minis.conf
systemctl daemon-reload
ln -s "$release" "$next"
mv -Tf "$next" /opt/minis/current
[ ! -e /usr/local/share/minis/mtls ] || [ -L /usr/local/share/minis/mtls ]
ln -sfn /opt/minis/current/mtls /usr/local/share/minis/mtls
systemctl restart minis.socket
if systemctl restart minis.service; then
    attempt=0
    ready=0
    while [ "$attempt" -lt 30 ]; do
        attempt=$((attempt + 1))
        if curl --silent --fail --max-time 3 --unix-socket /run/minis-edge/uq.sock \
            -H "Host: uni.keysi.dev" http://localhost/api/health >/dev/null &&
            systemctl is-active --quiet minis.service minis.socket; then
            ready=1
            break
        fi
        sleep 1
    done
    [ "$ready" -eq 1 ]
    systemctl restart caddy.service
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        attempt=$((attempt + 1))
        if curl --silent --fail --max-time 3 --unix-socket /run/minis-edge/caddy.sock \
            -H "Host: minis-origin.keysi.dev" http://localhost/api/health >/dev/null &&
            systemctl is-active --quiet caddy.service && soc_ready; then
            if [ -f /etc/cloudflared/minis.json ] && [ -f /etc/cloudflared/minis.env ]; then
                systemctl restart cloudflared-minis.service
                systemctl is-active --quiet cloudflared-minis.service
            fi
            systemctl enable minis.socket caddy.service
            systemctl disable minis.service >/dev/null 2>&1 || true
            if [ -f /etc/cloudflared/minis.json ] && [ -f /etc/cloudflared/minis.env ]; then
                systemctl enable cloudflared-minis.service
            fi
            trap - 0 1 2 15
            printf 'Minis release %s is healthy behind private Unix sockets\n' "$revision"
            exit 0
        fi
        sleep 1
    done
fi
exit 1
