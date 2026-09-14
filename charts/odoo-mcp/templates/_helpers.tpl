{{/*
Helper templates for the odoo-mcp chart.

Object names are derived from .Values.baseName, NOT from the release name: the
Cloudflare tunnel and the nginx proxy route to these exact Service names, and
changing a selector or a pod-template label would restart every pod.
*/}}

{{/*
The namespace EVERY object of this release lives in: always the release
namespace, i.e. exactly what `-n` / `--namespace` says. `namespace.name` is
deliberately NOT consulted here: a values file or a stray `--set` must never be
able to retarget the rendered objects at another (production) namespace while
the release record stays in the one `-n` names.
*/}}
{{- define "odoo-mcp.ns" -}}
{{ .Release.Namespace }}
{{- end -}}

{{/*
Name of the Namespace OBJECT this chart may create (namespace.yaml only). It
can never move this release's own objects - see "odoo-mcp.ns".
*/}}
{{- define "odoo-mcp.namespaceName" -}}
{{ default .Release.Namespace .Values.namespace.name }}
{{- end -}}

{{- define "odoo-mcp.name" -}}
{{ required "baseName must not be empty" .Values.baseName }}
{{- end -}}

{{- define "odoo-mcp.proxyName" -}}
{{ include "odoo-mcp.name" . }}-proxy
{{- end -}}

{{- define "odoo-mcp.adminName" -}}
{{ include "odoo-mcp.name" . }}-admin
{{- end -}}

{{- define "odoo-mcp.policyConfigMap" -}}
{{ include "odoo-mcp.name" . }}-policy
{{- end -}}

{{- define "odoo-mcp.patchConfigMap" -}}
{{ include "odoo-mcp.name" . }}-patch
{{- end -}}

{{/* nginx ConfigMap: rendered by this chart, or an existing one. */}}
{{- define "odoo-mcp.proxyConfigMap" -}}
{{- if .Values.proxy.config.create -}}
{{ include "odoo-mcp.proxyName" . }}-config
{{- else -}}
{{ default (printf "%s-config" (include "odoo-mcp.proxyName" .)) .Values.proxy.config.existingConfigMap }}
{{- end -}}
{{- end -}}

{{- define "odoo-mcp.dataClaim" -}}
{{ default .Values.persistence.name .Values.persistence.existingClaim }}
{{- end -}}

{{/* `labels:` block, or nothing. Never used on pod templates. */}}
{{- define "odoo-mcp.labels" -}}
{{- if .Values.extraLabels -}}
labels:
{{ toYaml .Values.extraLabels | indent 2 }}
{{- end -}}
{{- end -}}

{{/* `annotations:` block with the keep policy, or nothing. */}}
{{- define "odoo-mcp.keepAnnotations" -}}
{{- if .Values.keepOnUninstall -}}
annotations:
  helm.sh/resource-policy: keep
{{- end -}}
{{- end -}}

{{/* storageClassName for a component: its own override or the global default. */}}
{{- define "odoo-mcp.storageClass" -}}
{{- $ctx := index . 0 -}}
{{- $override := index . 1 -}}
{{ default $ctx.Values.storageClassName $override }}
{{- end -}}

{{- define "odoo-mcp.allowedHosts" -}}
{{- $hosts := .Values.server.allowedHosts -}}
{{- if not $hosts -}}
{{- fail "server.allowedHosts must list at least one host: an empty list makes every streamable-HTTP request fail the DNS-rebinding check" -}}
{{- end -}}
{{ join "," $hosts }}
{{- end -}}

{{/* The MCP proxy token. Required whenever this chart renders the nginx config. */}}
{{- define "odoo-mcp.authToken" -}}
{{ required "proxy.config.authToken is required when proxy.config.create=true (never commit it - pass it with --set or a values file kept outside the repo)" .Values.proxy.config.authToken }}
{{- end -}}

{{/* Container command for the MCP server: optional patch run, then the server. */}}
{{- define "odoo-mcp.serverCommand" -}}
{{- $args := printf "--transport %s --host 0.0.0.0 --port %v --path %s" .Values.server.transport (.Values.server.port | toString) .Values.server.path -}}
{{- if eq (.Values.server.allowRemoteHttp | toString) "1" -}}
{{- $args = printf "%s --allow-remote-http" $args -}}
{{- end -}}
{{- if .Values.server.inProcessAdmin.enabled -}}
{{- /*
Third runtime shape, and the most common one live: the MCP server and the admin
API run in the SAME container - `odoo-mcp` backgrounded, then uvicorn exec'd as
PID 1 - instead of the admin being its own Deployment. Six tenants run exactly
this, byte for byte. Note it invokes the `odoo-mcp` console script, not
`python3 -m odoo_mcp`, and applies no patches.
*/ -}}
{{ printf "odoo-mcp %s &\nexec uvicorn odoo_mcp_admin.main:app --host 0.0.0.0 --port %v\n" $args (.Values.server.inProcessAdmin.port | toString) }}
{{- else if .Values.server.applyPatches -}}
{{- $cmds := list "echo \"Applying WOOWTECH patches...\"" -}}
{{- range $p, $_ := .Files.Glob "files/patches/*.py" -}}
{{- $cmds = append $cmds (printf "python3 /app/patches/%s" (base $p)) -}}
{{- end -}}
{{- $cmds = append $cmds "echo \"Starting MCP server...\"" -}}
{{- $cmds = append $cmds (printf "exec python3 -m odoo_mcp %s" $args) -}}
{{- /*
Two vintages of this command are live and they differ ONLY in whitespace: some
tenants were applied from a one-line string, others from a shell script with
backslash continuations and a trailing newline. Whitespace is still part of the
pod template, so the style has to be selectable or the takeover rolls the pod.
*/ -}}
{{- if eq .Values.server.patchCommandStyle "continuation" -}}
{{ printf "%s\n" (join " \\\n&& " $cmds) }}
{{- else -}}
{{ join " && " $cmds }}
{{- end -}}
{{- else -}}
{{ printf "exec python3 -m odoo_mcp %s" $args }}
{{- end -}}
{{- end -}}
