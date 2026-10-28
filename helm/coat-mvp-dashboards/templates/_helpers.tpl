{{/*
Expand the name of the chart.
*/}}
{{- define "application.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "application.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "application.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "application.labels" -}}
helm.sh/chart: {{ include "application.chart" . }}
{{ include "application.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "application.selectorLabels" -}}
app.kubernetes.io/name: {{ include "application.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Dashboard resource full name.
Context: dict "root" $ "key" $key "dashboard" $dashboard
*/}}
{{- define "application.dashboard.fullname" -}}
{{- $name := required (printf "app.deployment.dashboards.%s.name is required" .key) .dashboard.name -}}
{{- $name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Dashboard selector labels.
*/}}
{{- define "application.dashboard.selectorLabels" -}}
{{- $name := required (printf "app.deployment.dashboards.%s.name is required" .key) .dashboard.name -}}
app.kubernetes.io/name: {{ $name }}
app.kubernetes.io/instance: {{ $name }}
{{- end }}

{{/*
Dashboard labels.
*/}}
{{- define "application.dashboard.labels" -}}
helm.sh/chart: {{ include "application.chart" .root }}
{{ include "application.dashboard.selectorLabels" . }}
{{- if .root.Chart.AppVersion }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end }}