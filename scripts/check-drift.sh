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
# Reported per object:
#   SAME       every field equal after server-side defaults are normalised away
#   INTENDED   the only differences are the declared, justified ones (the PVC's
#              helm.sh/resource-policy: keep) - still a pass
#   DRIFT      anything else, printed as a field-by-field list
#   MISSING    the chart renders an object that is not in the cluster
# Then a coverage pass the other way round, so an object the chart fails to
# produce at all cannot hide: every live mcp-* object is either compared above,
# REFERENCED by the render (an existing Secret/ConfigMap/PVC the chart mounts but
# deliberately does not own), or UNCOVERED - which fails.
#
# Extra arguments go to `helm template`, e.g. --set proxy.config.create=true.
set -euo pipefail

CONTEXT="${CONTEXT:-woow-k3s}"
NAMESPACE="${NAMESPACE:-komibright}"
RELEASE="${RELEASE:-mcp-odoo}"
# Name prefix of the objects this repo owns in a tenant namespace, for the
# coverage pass. COVERAGE=0 skips that pass.
PREFIX="${PREFIX:-mcp-}"
COVERAGE="${COVERAGE:-1}"
cd "$(dirname "$0")/.."
VALUES="${VALUES:-charts/odoo-mcp/deploy/woow-k3s/${NAMESPACE}.yaml}"

[ -f "$VALUES" ] || { echo "no instance values at $VALUES (set VALUES=...)"; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

helm template "$RELEASE" charts/odoo-mcp -n "$NAMESPACE" -f "$VALUES" --skip-tests "$@" \
  > "$tmp/repo.yaml"

CONTEXT="$CONTEXT" NAMESPACE="$NAMESPACE" PREFIX="$PREFIX" COVERAGE="$COVERAGE" \
  python3 - "$tmp/repo.yaml" <<'PY'
import json, os, re, subprocess, sys
import yaml

ctx, ns = os.environ["CONTEXT"], os.environ["NAMESPACE"]
prefix, coverage = os.environ["PREFIX"], os.environ["COVERAGE"] != "0"

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
# NOT normalised away: they show up in the output as INTENDED so the list stays
# honest, and anything outside it is drift.
INTENDED = {("PersistentVolumeClaim", "metadata.annotations.helm.sh/resource-policy")}
# Live objects the chart mounts by name and deliberately does not render.
REF_PARENTS = {"secretKeyRef", "configMapKeyRef", "secretRef", "configMapRef",
               "configMap", "secret", "persistentVolumeClaim"}
COVER_KINDS = ["deployment", "service", "configmap", "persistentvolumeclaim",
               "secret"]


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


MISSING = type("Missing", (), {"__repr__": lambda self: "<absent>"})()


def diffs(live, chart, path=""):
    """(path, live value, chart value) for every leaf that differs.

    A dict present on one side only is still walked key by key, so an annotation
    the chart adds is reported as metadata.annotations.<key> and can be matched
    against INTENDED instead of collapsing into a whole-block difference.
    """
    if live is chart or (live is not MISSING and chart is not MISSING and live == chart):
        return
    if (live is MISSING or isinstance(live, dict)) and (chart is MISSING or isinstance(chart, dict)) \
            and (isinstance(live, dict) or isinstance(chart, dict)):
        l = live if isinstance(live, dict) else {}
        c = chart if isinstance(chart, dict) else {}
        for k in sorted(set(l) | set(c)):
            p = "%s.%s" % (path, k) if path else k
            yield from diffs(l.get(k, MISSING), c.get(k, MISSING), p)
        return
    if isinstance(live, list) and isinstance(chart, list) and len(live) == len(chart):
        for i, (a, b) in enumerate(zip(live, chart)):
            yield from diffs(a, b, "%s[%d]" % (path, i))
        return
    yield (path, live, chart)


def token_of(doc):
    if doc.get("kind") != "ConfigMap":
        return None
    m = re.search(r"location /private_([^/]+)/", (doc.get("data") or {}).get("nginx.conf", ""))
    return m.group(1) if m else None


def referenced(o, out):
    """Names of Secrets/ConfigMaps/PVCs the rendered objects mount by name."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in REF_PARENTS and isinstance(v, dict):
                for nk in ("name", "secretName", "claimName"):
                    if isinstance(v.get(nk), str):
                        out.add(v[nk])
            if k == "imagePullSecrets" and isinstance(v, list):
                for e in v:
                    if isinstance(e, dict) and isinstance(e.get("name"), str):
                        out.add(e["name"])
            referenced(v, out)
    elif isinstance(o, list):
        for e in o:
            referenced(e, out)


def get(kind, name=None):
    target = kind if name is None else "%s/%s" % (kind, name)
    r = subprocess.run(["kubectl", "--context", ctx, "-n", ns, "get", target, "-o", "json"],
                       capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


rc = 0
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d]
secrets_seen = {t for t in (token_of(d) for d in docs) if t}
rendered, refs = set(), set()
referenced(docs, refs)


def redact(s):
    for t in secrets_seen:
        s = s.replace(t, "<REDACTED>")
    return s


def say(label, kind, name, note=""):
    print("%-10s %-22s %s%s" % (label, kind, name, note))


def field(f):
    print(redact("           %s: live=%r chart=%r" % f))


for d in docs:
    kind, name = d["kind"], d["metadata"]["name"]
    rendered.add((kind, name))
    live = get(kind.lower(), name)
    if live is None:
        say("MISSING", kind, name)
        rc = 1
        continue
    tok = token_of(live)
    if tok:
        secrets_seen.add(tok)
    found = list(diffs(norm(live), norm(d)))
    wanted = [f for f in found if (kind, f[0]) in INTENDED]
    unwanted = [f for f in found if (kind, f[0]) not in INTENDED]
    if unwanted:
        say("DRIFT", kind, name)
        rc = 1
        for f in unwanted:
            field(f)
        for f in wanted:
            field(f)
    elif wanted:
        say("INTENDED", kind, name)
        for f in wanted:
            field(f)
    else:
        say("SAME", kind, name)

# Coverage the other way round: a live object the chart never renders.
if coverage:
    for kind in COVER_KINDS:
        lst = get(kind)
        for o in (lst or {}).get("items", []):
            name = o["metadata"]["name"]
            k = o.get("kind") or re.sub(r"List$", "", lst.get("kind", ""))
            if not name.startswith(prefix) or (k, name) in rendered:
                continue
            if name in refs:
                say("REFERENCED", k, name, "  (mounted by name, not owned - by design)")
            else:
                say("UNCOVERED", k, name, "  (live, but the chart renders nothing for it)")
                rc = 1
sys.exit(rc)
PY
