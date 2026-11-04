# iPad LAN HTTPS candidate

**Prepared configuration only, November 4, 2026. Not installed or activated.** No Caddy binary, CA, certificate, private key, trust profile, firewall change, or service state is supplied by these files. Operational session (7) owns any installation, first start, device enrollment, and actual verification. Do not start or restart the application, camera, robot API, RODI host, or a mission to test this proxy.

Browser microphone capture requires a secure context. The current plain-LAN HTTP address is not the localhost exception. This candidate adds `https://192.168.10.31:8443/`, using a device-trusted local CA, while leaving the existing HTTP endpoint and application process unchanged. It does not make HTTP microphone-ready. See [MDN microphone requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

## Scope and prerequisites

- The existing application is already listening on `127.0.0.1:8080`; the reviewed LAN IP is still `192.168.10.31`, and TCP port `8443` is unused.
- A separately approved, version/hash-recorded Linux ARM64 Caddy binary is available at `/usr/bin/caddy`. No download or package installation command is included. Review the exact installed version against [official Caddy distribution guidance](https://caddyserver.com/docs/install).
- The operational owner can manually approve first start, which creates CA/key material in the private data directory. The owner can transfer **only the public root certificate** through an authenticated channel, and the iPad owner can install and explicitly trust it. Device trust is not automatic.
- Keep this endpoint within the existing reviewed LAN access scope. Do not add a public tunnel, router forwarding, wildcard listener, client authentication bypass, or provider key to the browser. The proxy retains the application's existing access controls; it does not add user authentication. Devices that can reach this LAN endpoint have the same application API exposure as the existing reviewed HTTP LAN endpoint, including configured physical controls.
- Preserve existing mission/database/profile/camera state. Proxy activation cannot establish robot readiness, approve a plan, restore a mission, or authorize motion.

`Caddyfile.example` binds only the specified LAN interface and port. It disables the admin API, configuration persistence, automatic system trust installation, HTTP redirects/listeners, and HTTP/3. Metrics are not enabled. TLS defaults remain Caddy's defaults. See [global options](https://caddyserver.com/docs/caddyfile/options), [interface binding](https://caddyserver.com/docs/caddyfile/directives/bind), and [internal TLS](https://caddyserver.com/docs/caddyfile/directives/tls).

## Same-origin proxy behavior

Every path goes to the one existing loopback application. Relative API, image, font, asset, and WebSocket URLs therefore keep the browser's HTTPS origin. Do not hardcode the old HTTP LAN origin in the frontend. Caddy preserves the request Host and provides its normal trusted forwarding headers. The backend's `physical_api.same_origin` compares the browser Origin against the ASGI scheme and Host: verify that Uvicorn trusts only this loopback proxy's forwarded scheme. Never weaken that guard, remove Origin, or rewrite it to pass a test.

There is no retry window or retry count, alternate upstream, active health request, or request replay queue. Upstream keepalive is off to avoid stale-connection transport retries. No request/response body buffer or encoder is enabled. Positive `flush_interval 50ms` keeps camera/multipart output flowing while preserving upstream cancellation when clients disconnect; recognized SSE responses flush immediately. WebSocket upgrades pass through. Application-owned upload/provider limits remain authoritative; no proxy response-header or stream lifetime timeout is added. See [Caddy reverse proxy behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

This setup adds transport security, not JPEG re-encoding, image warping, or camera inference. Compare exact original-frame bytes/hash during activation rather than treating a visible preview as proof of unchanged quality. Do not enable access/debug logs that retain voice payloads, transcripts, credentials, or private query strings.

## Manual staging and validation

The following are **operator-run examples**, not a deployment script. They are not executed by the application. Run as the reviewed application user. Keep the current Caddyfile/data directory if already provisioned; do not overwrite another installation or rotate the CA as a shortcut. The example paths require `/usr/bin/caddy`; adjust a reviewed binary path before staging if necessary.

```sh
install -d -m 0700 "$HOME/.config/pushpilot-ipad-https"
install -d -m 0700 "$HOME/.local/share/pushpilot-ipad-https"
install -d -m 0700 "$HOME/.config/systemd/user"
install -m 0600 deploy/ipad-https/Caddyfile.example "$HOME/.config/pushpilot-ipad-https/Caddyfile"
install -m 0600 deploy/ipad-https/pushpilot-ipad-https.service.example "$HOME/.config/systemd/user/pushpilot-ipad-https.service"
```

Before starting anything, record binary version/hash, config hash, existing listening sockets, and the intended upstream owner. Adaptation parses without starting a listener; do **not** use `--validate` during the no-certificate-generation preparation phase because provisioning validation may create local PKI state.

```sh
/usr/bin/caddy version
sha256sum /usr/bin/caddy "$HOME/.config/pushpilot-ipad-https/Caddyfile"
PUSHPILOT_HTTPS_DATA_DIR="$HOME/.local/share/pushpilot-ipad-https" \
  /usr/bin/caddy adapt --config "$HOME/.config/pushpilot-ipad-https/Caddyfile" --adapter caddyfile --pretty
systemd-analyze --user verify "$HOME/.config/systemd/user/pushpilot-ipad-https.service"
```

Inspect adapted JSON: one listener `192.168.10.31:8443`, admin disabled, internal issuer, no public ACME issuer, one upstream `127.0.0.1:8080`, zero retries, and no unexpected routes. Runtime socket inspection remains necessary because automatic server setup happens after adaptation. These files have not been parsed with a Caddy executable in the development workspace; exact-version adaptation is an outstanding gate.

After separate operational approval, the owner may load and manually start **only this new unit**:

```sh
systemctl --user daemon-reload
systemctl --user start pushpilot-ipad-https.service
systemctl --user status pushpilot-ipad-https.service --no-pager
```

There is no `[Install]` section, `enable`, linger change, `Restart=always`, watched configuration, or service dependency that starts application/robot processes. `--resume=false` prevents reusing a saved Caddy configuration instead of the reviewed file. First start deliberately provisions local PKI; routine later starts retain that CA. The unit is an adaptation of [Caddy's systemd guidance](https://caddyserver.com/docs/running), using the documented [foreground command](https://caddyserver.com/docs/command-line#caddy-run).

## Public root export and iPad enrollment

Caddy stores its local root at `pki/authorities/local/root.crt` under the explicit data directory. Never export `root.key`, intermediate keys, the complete data directory, or an unredacted configuration/environment. Keep storage owner-private and backed up through the existing private process; losing it and generating another CA invalidates the enrolled trust relationship. See [Caddy local HTTPS and storage](https://caddyserver.com/docs/automatic-https#local-https).

After approved first start, an owner can inspect and copy the **public** root certificate:

```sh
openssl x509 -in "$HOME/.local/share/pushpilot-ipad-https/pki/authorities/local/root.crt" \
  -noout -subject -issuer -dates -fingerprint -sha256
openssl x509 -in "$HOME/.local/share/pushpilot-ipad-https/pki/authorities/local/root.crt" \
  -outform DER -out "$HOME/.config/pushpilot-ipad-https/PushPilot-iPad-LAN-root.cer"
sha256sum "$HOME/.config/pushpilot-ipad-https/PushPilot-iPad-LAN-root.cer"
```

Transfer that `.cer` through an already authenticated channel or direct physical transfer. Provide its SHA-256 fingerprint through an independently authenticated channel and verify it before enrollment; an unauthenticated LAN download alone is not a trust check. Do not expose the CA storage with `file_server` or a new public certificate-download server.

On the iPad, open the verified certificate, install its downloaded profile in **Settings > General > VPN & Device Management**, then use **Settings > General > About > Certificate Trust Settings** to enable full SSL trust for that exact root. Confirm its identity against the recorded fingerprint, not merely its display name. These steps need the device owner and may need the iPad passcode; no password belongs in chat or a script. Apple documents that manual profile installation alone does not establish SSL trust. See [Apple's certificate-trust instructions](https://support.apple.com/en-us/102390).

Open `https://192.168.10.31:8443/` directly in Safari and accept the browser's normal microphone permission prompt after tapping the application's mic button. **Do not bypass a certificate warning.** A warning, changed fingerprint, wrong address, or `isSecureContext === false` blocks microphone readiness; retain text entry and report the cause. Private PKI cannot be described as trusted until the actual device completes this step.

## Acceptance and rollback

Before reporting ready, the owner records:

1. Only the intended TCP listener was added; no wildcard/admin/HTTP redirect/UDP listener, public exposure, or extra camera/RODI port was created.
2. A certificate-validating client can GET the app and health API using the recorded root (`curl --cacert <root.crt>`, never `-k`). The actual iPad opens the exact HTTPS URL without warnings and secure-context preflight passes.
3. Assets, camera originals, polling/SSE/stream paths and cancellation remain usable over HTTPS. Original selected JPEG bytes/hash match upstream; no compression or re-encoding was introduced.
4. Scheme/Host forwarding preserves the existing same-origin guard. Verify this offline or through the established non-motion procedure, not by probing a live Start/Stop/Reset endpoint.
5. Actual iPad permission, record/stop/cancel, mic release, waveform, upload, editable result, denial and text fallback pass. HTTP success or local desktop tests do not prove this device gate or Meta account voice access.
6. Existing application PID, robot/camera processes, mission/receipt/profile/camera bindings and active-command count are unchanged. No mission was run as a deployment test.

For rollback, stop **only** `pushpilot-ipad-https.service`; this closes the added port and does not stop or restart PushPilot. Do not remove CA/private data or restore an old database. If permanently retiring this CA, the device owner can remove its iPad profile after confirming no other enrolled client needs it. Keep the existing HTTP path for typed-goal access, never claim its microphone is available. Proxy shutdown interrupts active browser connections, so schedule it outside voice capture and robot operation.

```sh
systemctl --user stop pushpilot-ipad-https.service
```
