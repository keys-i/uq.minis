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
install -d -m 755 /opt/minis/releases
exec 9>/opt/minis/deploy.lock
flock -n 9
getent passwd minis >/dev/null || useradd --system --home-dir /var/lib/minis --shell /usr/sbin/nologin minis
install -d -m 700 /var/lib/minis
chown minis:minis /var/lib/minis
release=/opt/minis/releases/$revision
mkdir "$release"
cp -R "$stage/frontend" "$release/frontend"
# Keep managed Python outside root's home so ProtectHome can remain enabled
export UV_PYTHON_INSTALL_DIR=/opt/minis/python
uv venv --managed-python --python 3.15 "$release/.venv"
uv pip sync --python "$release/.venv/bin/python" --compile-bytecode --require-hashes "$stage/requirements.txt"
uv pip install --python "$release/.venv/bin/python" --no-deps --compile-bytecode "$stage/"*.whl
install -d -m 755 /opt/minis/browsers
PLAYWRIGHT_BROWSERS_PATH=/opt/minis/browsers "$release/.venv/bin/playwright" install chromium
chmod -R a+rX /opt/minis/browsers

previous=$(readlink /opt/minis/current || true)
unit=/etc/systemd/system/minis.service
next=/opt/minis/.next-$revision
if [ -f "$unit" ]; then cp "$unit" "$stage/previous.service"; fi
for name in minis@.service minis@.socket; do
    if [ -f "/etc/systemd/system/$name" ]; then cp "/etc/systemd/system/$name" "$stage/previous.$name"; fi
done
if [ -f /etc/polkit-1/rules.d/50-minis.rules ]; then cp /etc/polkit-1/rules.d/50-minis.rules "$stage/previous.rules"; fi
rollback() {
    status=$?
    trap - 0 1 2 15
    rm -f "$next"
    if [ -f "$stage/previous.service" ]; then
        install -m 644 "$stage/previous.service" "$unit"
    else
        rm -f "$unit"
    fi
    for name in minis@.service minis@.socket; do
        if [ -f "$stage/previous.$name" ]; then
            install -m 644 "$stage/previous.$name" "/etc/systemd/system/$name"
        else
            rm -f "/etc/systemd/system/$name"
        fi
    done
    if [ -f "$stage/previous.rules" ]; then
        install -m 644 "$stage/previous.rules" /etc/polkit-1/rules.d/50-minis.rules
    else
        rm -f /etc/polkit-1/rules.d/50-minis.rules
    fi
    systemctl daemon-reload
    if [ -n "$previous" ]; then
        ln -s "$previous" "$next"
        mv -Tf "$next" /opt/minis/current
        systemctl restart minis
    else
        systemctl stop minis
        rm -f /opt/minis/current
    fi
    printf 'New release failed; previous code restored and private state preserved\n' >&2
    exit "$status"
}
trap rollback 0
trap 'exit 1' 1 2 15
install -m 644 "$stage/minis@.service" /etc/systemd/system/minis@.service
install -m 644 "$stage/minis@.socket" /etc/systemd/system/minis@.socket
install -m 644 "$stage/minis.rules" /etc/polkit-1/rules.d/50-minis.rules
install -m 644 "$stage/minis.service" /etc/systemd/system/minis.service
systemctl daemon-reload
ln -s "$release" "$next"
mv -Tf "$next" /opt/minis/current
if systemctl restart minis; then
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        attempt=$((attempt + 1))
        if curl --silent --fail --max-time 3 -H "Host: uni.keysi.dev" http://127.0.0.1:8765/api/session >/dev/null &&
            systemctl is-active --quiet minis; then
            systemctl enable minis
            trap - 0 1 2 15
            printf 'Minis release %s is running privately on 127.0.0.1:8765\n' "$revision"
            exit 0
        fi
        sleep 1
    done
fi
exit 1
