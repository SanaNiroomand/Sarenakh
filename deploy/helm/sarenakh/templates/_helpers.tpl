{{- define "sarenakh.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "sarenakh.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "sarenakh.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "sarenakh.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sarenakh.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "sarenakh.labels" -}}
helm.sh/chart: {{ include "sarenakh.chart" . }}
{{ include "sarenakh.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "sarenakh.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "sarenakh.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "sarenakh.secretName" -}}
{{- default (include "sarenakh.fullname" .) .Values.secret.existingSecret }}
{{- end }}

{{- define "sarenakh.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion | toString) }}
{{- end }}

{{/* "true"/"false" for COOKIE_SECURE; auto = HTTPS ingress configured */}}
{{- define "sarenakh.cookieSecure" -}}
{{- if eq (toString .Values.cookieSecure) "auto" }}
{{- ternary "true" "false" (and .Values.ingress.enabled (gt (len .Values.ingress.tls) 0)) }}
{{- else }}
{{- toString .Values.cookieSecure | lower }}
{{- end }}
{{- end }}
