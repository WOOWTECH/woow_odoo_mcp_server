#!/usr/bin/env bash
# Compare charts/odoo-mcp with what is running, for one Odoo tenant.
# Exit 0 = the chart renders the live objects, 1 = drift.
#
#   CONTEXT=woow-k3s NAMESPACE=komibright RELEASE=mcp-odoo scripts/check-drift.sh
#
# Reads the cluster only: `kubectl get -o json` plus `helm template`. Nothing is
# applied, and no secret value is printed - the MCP proxy token is redacted from
# any diff, and the nginx ConfigMap is only compared when you pass the token in
# yourself (--set proxy.config.create=true,proxy.config.authToken=...).
#
# Extra arguments go to `helm template`, e.g. --set proxy.config.create=true.
set -euo pipefail

CONTEXT="${CONTEXT:-woow-k3s}"
NAMESPACE="${NAMESPACE:-komibright}"
RELEASE="${RELEASE:-mcp-odoo}"
cd "$(dirname "$0")/.."
VALUES="${VALUES:-charts/odoo-mcp/deploy/woow-k3s/${NAMESPACE}.yaml}"

[ -f "$VALUES" ] || { echo "no instance values at $VALUES (set VALUES=...)"; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

helm template "$RELEASE" charts/odoo-mcp -n "$NAMESPACE" -f "$VALUES" --skip-tests "$@" \
  > "$tmp/repo.yaml"

CONTEXT="$CONTEXT" NAMESPACE="$NAMESPACE" python3 - "$tmp/repo.yaml" <<'PY'
import json, os, re, subprocess, sys, difflib
import yaml

ctx, ns = os.environ["CONTEXT"], os.environ["NAMESPACE"]

DROP_META = {"creationTimestamp", "generation", "resourceVersion", "uid",
             "managedFields", "selfLink", "finalizers"}
DROP_ANN = {"kubectl.kubernetes.io/last-applied-configuration",
            "deployment.kubernetes.io/revision",
            "pv.kubernetes.io/bind-completed", "pv.kubernetes.io/bound-by-controller",
            "volume.beta.kubernetes.io/storage-provisioner",
            "volume.kubernetes.io/storage-provisioner"}
# Fields the API server fills in. Dropped from BOTH sides so the comparison is
# about what the chart declares, not about Kubernetes defaulting.
DEFAULTS_POD = {"dnsPolicy": "ClusterFirst", "restartPolicy": "Always",
                "schedulerName": "default-scheduler", "securityContext": {},
                "terminationGracePeriodSeconds": 30}
DEFAULTS_CTR = {"terminationMessagePath": "/dev/termination-log",
                "terminationMessagePolicy": "File"}
# Intended, justified differences (see charts/odoo-mcp/README.md "Takeover").
INTENDED = {("PersistentVolumeClaim", "metadata.annotations.helm.sh/resource-policy")}


def drop(d, key, default):
    if isinstance(d, dict) and key in d and d[key] == default:
        del d[key]


def norm(o):
    o = json.loads(json.dumps(o))
    o.pop("status", None)
    m = o.setdefault("metadata", {})
    for k in list(m):
        if k in DROP_META:
            del m[k]
    ann = m.get("annotations") or {}
    for k in list(ann):
        if k in DROP_ANN:
            del ann[k]
    # helm.sh/resource-policy exists only on the chart side, on purpose.
    ann.pop("helm.sh/resource-policy", None)
    if not ann:
        m.pop("annotations", None)
    sp = o.get("spec") or {}
    kind = o["kind"]
    if kind == "Deployment":
        drop(sp, "progressDeadlineSeconds", 600)
        drop(sp, "revisionHistoryLimit", 10)
        drop(sp, "strategy", {"rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"},
                              "type": "RollingUpdate"})
        pod = sp.get("template", {}).get("spec", {})
        for k, v in DEFAULTS_POD.items():
            drop(pod, k, v)
        for c in (pod.get("containers") or []) + (pod.get("initContainers") or []):
            for k, v in DEFAULTS_CTR.items():
                drop(c, k, v)
            for p in c.get("ports") or []:
                drop(p, "protocol", "TCP")
            for probe in ("livenessProbe", "readinessProbe", "startupProbe"):
                pr = c.get(probe)
                if not pr:
                    continue
                drop(pr, "failureThreshold", 3)
                drop(pr, "successThreshold", 1)
                drop(pr, "timeoutSeconds", 1)
                drop(pr.get("httpGet") or {}, "scheme", "HTTP")
        for v in pod.get("volumes") or []:
            drop(v.get("configMap") or {}, "defaultMode", 420)
            drop(v.get("secret") or {}, "defaultMode", 420)
    elif kind == "Service":
        for f in ("clusterIP", "clusterIPs", "internalTrafficPolicy", "ipFamilies",
                  "ipFamilyPolicy"):
            sp.pop(f, None)
        drop(sp, "sessionAffinity", "None")
        drop(sp, "type", "ClusterIP")
        for p in sp.get("ports") or []:
            drop(p, "protocol", "TCP")
    elif kind == "PersistentVolumeClaim":
        drop(sp, "volumeMode", "Filesystem")
        sp.pop("volumeName", None)
    return o


def token_of(doc):
    if doc.get("kind") != "ConfigMap":
        return None
    m = re.search(r"location /private_([^/]+)/", (doc.get("data") or {}).get("nginx.conf", ""))
    return m.group(1) if m else None


rc = 0
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d]
secrets_seen = [t for t in (token_of(d) for d in docs) if t]
for d in docs:
    kind, name = d["kind"], d["metadata"]["name"]
    got = subprocess.run(["kubectl", "--context", ctx, "-n", ns, "get",
                          kind.lower() + "/" + name, "-o", "json"],
                         capture_output=True, text=True)
    if got.returncode != 0:
        print("MISSING  %-22s %s" % (kind, name))
        rc = 1
        continue
    live = json.loads(got.stdout)
    tok = token_of(live)
    if tok:
        secrets_seen.append(tok)
    a = yaml.safe_dump(norm(live), sort_keys=True, width=10 ** 6)
    b = yaml.safe_dump(norm(d), sort_keys=True, width=10 ** 6)
    if a == b:
        print("SAME     %-22s %s" % (kind, name))
    else:
        print("DRIFT    %-22s %s" % (kind, name))
        rc = 1
        out = "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                           "live/" + name, "chart/" + name))
        for t in set(secrets_seen):
            out = out.replace(t, "<REDACTED>")
        print(out)
sys.exit(rc)
PY
