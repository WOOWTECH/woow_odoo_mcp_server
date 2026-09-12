# charts/odoo-mcp

Helm chart for **one Odoo tenant's MCP server** on K3s. It replaces the old
root-level `k8s-deploy.yaml`, which was a copy of a manifest applied by hand to a
single namespace (`kasim-odoo`), pinned an image this repo does not build, and
had already drifted away from every running tenant.

[正體中文](README_zh-TW.md)

One release per Odoo instance. The chart is independent of the Odoo tenant
itself: Odoo, PostgreSQL and the Cloudflare tunnel stay where they are.

---

## What it deploys

| Object | Name | Purpose |
|---|---|---|
| Deployment + Service | `mcp-odoo` | `python3 -m odoo_mcp`, streamable HTTP on `:8000/mcp`, after `patches/*.py` are applied at start |
| Deployment + Service | `mcp-odoo-proxy` | nginx token gate: only `/private_<token>/…` is forwarded, everything else is `403` |
| ConfigMap | `mcp-odoo-proxy-config` | the nginx config (contains the token — **not** rendered by default) |
| ConfigMap | `mcp-odoo-policy` | `odoo_mcp_policy.json`, the side-effect allow-list |
| ConfigMap | `mcp-odoo-patch` | the three WOOWTECH patches, mounted at `/app/patches` |
| PersistentVolumeClaim | `mcp-admin-data` | `/data` (optional) |
| Deployment + Service | `mcp-odoo-admin` | the FastAPI console from this repo (optional, off by default) |
| Secret | `mcp-odoo-secrets`, `mcp-odoo-admin-secret` | only with `secrets.create=true` |
| NetworkPolicy | `mcp-odoo-deny-external` | optional, off by default |

`baseName` renames all of them at once (a second MCP for another database is
`baseName: mcp-odoo-social`).

---

## Install

From a clone:

```bash
helm install mcp-odoo charts/odoo-mcp -n <tenant> \
  -f deploy/woow-k3s/<tenant>.yaml
```

From a GitHub tarball, without cloning. The chart lives in a subdirectory, so the
archive has to be unpacked first — `helm install <url>` only accepts an archive
whose `Chart.yaml` sits at the root, which a GitHub source archive never has:

```bash
REF=main   # any branch or tag
curl -fsSL "https://github.com/WOOWTECH/woow_odoo_mcp_server/archive/refs/heads/${REF}.tar.gz" | tar -xz
# GitHub names the extracted directory after the ref, with / replaced by -
SRC="woow_odoo_mcp_server-${REF//\//-}"   # the extracted repo

helm install mcp-odoo "$SRC/charts/odoo-mcp" -n <tenant> \
  -f "$SRC/deploy/woow-k3s/<tenant>.yaml"
```

For a tag, use `archive/refs/tags/${REF}.tar.gz` instead. CI re-runs this
unpack-then-install path on every push, so the snippet cannot rot.

A brand-new tenant, with the chart creating the credentials and the nginx config:

```bash
ODOO_PASSWORD=...            # the Odoo login the MCP uses
MCP_AUTH_TOKEN=$(python3 -c 'import secrets;print(secrets.token_hex(10))')

helm install mcp-odoo charts/odoo-mcp -n <tenant> --create-namespace \
  --set odoo.url=https://<tenant>-odoo.woowtech.io \
  --set odoo.db=<tenant> \
  --set "server.allowedHosts={<tenant>-mcp-odoo.woowtech.io,localhost,mcp-odoo-proxy.<tenant>.svc.cluster.local,mcp-odoo.<tenant>.svc.cluster.local,127.0.0.1}" \
  --set secrets.create=true --set secrets.odooPassword="$ODOO_PASSWORD" \
  --set proxy.config.create=true --set proxy.config.authToken="$MCP_AUTH_TOKEN"
```

The MCP endpoint is then
`http://mcp-odoo-proxy.<tenant>.svc.cluster.local:8001/private_<token>/mcp`,
which is what the tenant's Cloudflare tunnel points at.

### Key values

| Value | Default | Notes |
|---|---|---|
| `odoo.url`, `odoo.db` | — | **required**, no default |
| `server.allowedHosts` | `[]` | **required**; an empty list makes every request fail the DNS-rebinding check |
| `baseName` | `mcp-odoo` | prefix for every object |
| `namespace.create` / `.name` | `false` / release ns | names **only** the Namespace object; it never moves the release's own objects, which always follow `-n`. A namespace equal to the release namespace is never rendered |
| `keepOnUninstall` | `true` | `helm.sh/resource-policy: keep` on Namespace, PVC and chart-created Secrets |
| `storageClassName` | `longhorn` | `longhorn-delete` for throwaway tests, `local-path` on the laptop cluster |
| `secrets.create` | `false` | `true` renders the Secrets from `required()`-guarded values |
| `proxy.config.create` | `false` | `true` renders the nginx ConfigMap from `proxy.config.authToken` |
| `persistence.enabled` | `false` | `/data` PVC (1 Gi Longhorn in the live tenants) |
| `initConfig.enabled` | `false` | seed `/data/config.json` from an existing ConfigMap; needs `persistence.enabled` |
| `admin.enabled` | `false` | the FastAPI console on `:8080` |
| `networkPolicy.enabled` | `false` | the live tenants already have a namespace-wide policy |
| `server.podAnnotations` | `{}` | carries the live `kubectl.kubernetes.io/restartedAt` stamp |
| `nodeSelector` | `{}` | node placement for every pod, including the `helm test` pod; empty adds nothing to a live pod template |
| `tests.timeoutSeconds` | `180` | how long the smoke pod retries a connection before failing |

Full list with comments: [`values.yaml`](values.yaml).

### Secrets

`secrets.create: false` is the default: the chart **references** Secrets that
already exist, so no upgrade can overwrite a real password with an empty string.
Keys and placeholders: [`examples/secrets.example.yaml`](examples/secrets.example.yaml).

Two things never enter git:

* the Odoo password — Secret `mcp-odoo-secrets`, key `odoo-password`;
* the MCP proxy token — it is part of the nginx `location /private_<token>/`, so
  `proxy.config.create` is `false` and the chart mounts the ConfigMap that is
  already in the cluster. See [`examples/proxy-token.example.yaml`](examples/proxy-token.example.yaml).

`/data/config.json` in the live tenants (ConfigMap `mcp-admin-config`) holds the
console password, the MCP token and the Odoo password in clear text. The chart
**mounts** it and never renders it. Moving it to a Secret is a follow-up.

---

## Verify

```bash
kubectl -n <tenant> rollout status deploy/mcp-odoo
kubectl -n <tenant> rollout status deploy/mcp-odoo-proxy
helm test mcp-odoo -n <tenant> --logs
```

`helm test` runs a read-only smoke pod: the MCP server answers on `:8000`, the
proxy returns `403` without a token and forwards `/private_<token>/mcp` with one,
and the console answers `GET /healthz` when it is enabled. It reads the token
from the mounted ConfigMap, so the token never appears in a pod spec or an
audit log.

---

## Testing without the private image

`image.repository` (`ghcr.io/woowtech/woow-odoo-mcp-server`) is a **private**
GHCR package. It is pulled with the default `imagePullSecrets: [{name:
mcp-admin-ghcr}]`, and that Secret only exists in real tenant namespaces — it is
created once by hand per tenant, outside this chart. **Do not copy a tenant's
`mcp-admin-ghcr` (or any other production pull secret) into a test namespace**;
phase-1 rules only allow reusing one real org credential in a test (the
OpenRouter key, for a specific functional check elsewhere in this repo's
migration), and a GHCR pull secret is not that key.

The way that actually exercises the real image, and the one used to verify this
chart on `woow-k3s`:

* **Pin the pods to a node that already has the image cached.** Every node that
  runs a tenant's MCP already has `ghcr.io/woowtech/woow-odoo-mcp-server` in its
  containerd cache, so with `image.pullPolicy=IfNotPresent` and
  `imagePullSecrets: []` the kubelet never contacts ghcr.io and no credential is
  involved:

  ```bash
  # a node that runs an MCP pod today
  NODE=$(kubectl get pods -A -o jsonpath='{range .items[*]}{.spec.nodeName}{"\t"}{.spec.containers[0].image}{"\n"}{end}' \
         | grep woow-odoo-mcp-server | head -1 | cut -f1)

  helm install mcp-odoo charts/odoo-mcp -n ht-odoo-mcp --create-namespace \
    --set imagePullSecrets=null --set image.pullPolicy=IfNotPresent \
    --set nodeSelector."kubernetes\.io/hostname"="$NODE" \
    --set storageClassName=longhorn-delete \
    --set odoo.url=http://odoo-stub.ht-odoo-mcp.svc.cluster.local:8069 \
    --set odoo.db=testdb \
    --set "server.allowedHosts={localhost,127.0.0.1,mcp-odoo.ht-odoo-mcp.svc.cluster.local,mcp-odoo-proxy.ht-odoo-mcp.svc.cluster.local}" \
    --set secrets.create=true --set secrets.odooPassword="$(openssl rand -hex 16)" \
    --set proxy.config.create=true --set proxy.config.authToken="$(openssl rand -hex 10)"

  helm test mcp-odoo -n ht-odoo-mcp --logs
  ```

  `nodeSelector` is empty in every instance values file, so it adds nothing to a
  live pod template.

  Point `odoo.url` at a throwaway stub in the same namespace rather than at a
  real tenant: the MCP server connects to Odoo lazily, so `initialize` and
  `tools/list` work against a stub that only answers `/xmlrpc/2/*` and
  `/jsonrpc`.

* **App behaviour, out-of-cluster** — install the same `odoo-mcp` version the
  Dockerfile installs into a venv, apply `files/patches/*.py` unmodified, and
  run `python3 -m odoo_mcp --transport streamable-http …` directly; separately
  run `odoo_mcp_admin` with `uvicorn` and hit `/healthz`. This exercises the
  actual server and admin console without any cluster at all.

---

## Uninstall (data is kept)

```bash
helm uninstall mcp-odoo -n <tenant>
```

With `keepOnUninstall: true` (the default) the Namespace, the PVC and any
chart-created Secret carry `helm.sh/resource-policy: keep` and survive. Only the
Deployments, Services and the policy/patch ConfigMaps go away. The Odoo tenant is
untouched: the chart never owns Odoo, PostgreSQL or the tunnel.

To remove the data too, delete the PVC by hand afterwards.

---

## Takeover of a running tenant

The live tenants were created with `kubectl apply`, not Helm. The chart renders
those objects **exactly**, so adopting one restarts nothing:

```bash
CONTEXT=woow-k3s NAMESPACE=komibright RELEASE=mcp-odoo scripts/check-drift.sh
```

reads the live objects and compares them field by field against
`helm template … -f deploy/woow-k3s/komibright.yaml` (server defaults normalised
away on both sides, proxy token redacted from any output). Each object comes back
as `SAME`, `INTENDED` (only the declared, justified differences), `DRIFT` (with
the differing fields printed) or `MISSING`. A second pass goes the other way
round — every live `mcp-*` object must be either compared, `REFERENCED` (mounted
by name and deliberately not owned: `mcp-admin-config`, `mcp-odoo-proxy-config`,
`mcp-admin-ghcr`, `mcp-odoo-secrets`) or it is reported `UNCOVERED` and the script
fails, so an object the chart forgets cannot hide.

Current result for komibright: **7 SAME/INTENDED + 4 REFERENCED, exit 0** — and
8/8 when the nginx ConfigMap is included by passing the live token in
(`--set proxy.config.create=true --set proxy.config.authToken=…`).

The one intended difference: the PVC gains `helm.sh/resource-policy: keep`. It is
a metadata annotation, so it changes no pod template and rolls nothing.

When the comparison is clean, adopt with:

```bash
helm upgrade --install mcp-odoo charts/odoo-mcp -n <tenant> \
  -f deploy/woow-k3s/<tenant>.yaml --take-ownership
```

Then confirm no pod restarted (`kubectl get pods -o wide`, compare UIDs and
restart counts before and after).

### Instance values

`deploy/woow-k3s/<tenant>.yaml` holds one tenant's values, with no secrets.
Currently shipped: **komibright** — the standard shape.

The other tenants each drifted in their own direction after they were applied
(different env subsets, `emptyDir` instead of a PVC, the proxy volume named
`conf` instead of `config`, patches applied in some and not in others). Before a
tenant can be adopted, its values file has to be written and `check-drift.sh` has
to come back clean; where the drift is cosmetic, normalising the live object
first is the smaller change.

---

## Follow-ups (deliberately NOT in this chart)

These would change a running pod template, so they stay opt-in and off:

1. **`/data/config.json` holds credentials in a ConfigMap.** `initConfig.keepExisting: true`
   at least stops every restart from reverting a rotated console password and MCP
   token; moving the file into a Secret is the real fix.
2. **`imagePullPolicy: Always` on `:latest`.** The GHCR package publishes only
   `latest`, so any restart can silently change the running version — the drift
   this repo has already been bitten by. Pin a digest once the image is built by CI.
3. **No `securityContext`.** The image runs as root and the pod spec sets nothing
   (`runAsNonRoot`, `readOnlyRootFilesystem`, dropped capabilities).
4. **`automountServiceAccountToken`** is disabled on the console only. The MCP
   server pods still mount the default token.
5. **The MCP token travels in the URL path** and nginx logs the full request line,
   so anyone who can read the proxy's logs can read the token.
6. **`ODOO_MCP_ALLOW_UNKNOWN_METHODS=1`** in komibright widens the side-effect
   gate past `mcp-odoo-policy`. Narrowing it is a tenant decision, not a chart
   default.
7. **Rolling the server pod with `persistence.enabled: true` can deadlock.** The
   `/data` claim is ReadWriteOnce and the Deployment keeps the live
   `RollingUpdate` strategy, so the replacement pod is created before the old one
   goes away: if the scheduler puts it on another node it waits in
   `Multi-Attach error for volume …` until the old pod is gone (seen in a test
   install on woow-k3s; a live `kubectl rollout restart` only works while the new
   pod lands on the same node). `strategy: Recreate` fixes it but changes the live
   Deployment spec, so it is not in this chart. Until then, roll such a tenant with
   `kubectl scale deploy/mcp-odoo --replicas=0` and back to 1.
8. **No readiness probe on the MCP server.** The live Deployments have none, so
   the chart renders none: `kubectl rollout status` returns while uvicorn is still
   starting, and a Service endpoint exists before the port is open. The `helm test`
   pod works around it by retrying every connection up to `tests.timeoutSeconds`.
   Adding a probe would change the live pod template.
