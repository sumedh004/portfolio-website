# Portfolio Project — Troubleshooting & Fixes Reference
K3s on Oracle Cloud Always Free | Weeks 1–12

---

## 1. Traefik Middleware Annotation Format
**Problem:** Middleware annotations written as YAML block scalars caused Traefik to ignore them.
**Fix:** Middleware annotations must always be single-line strings, not multiline YAML block scalars.
**Lesson:** Traefik is strict about annotation format — always use `"namespace-middleware@kubernetescrd"` inline.

---

## 2. Broken nginx Log Format Blocking Python Metrics Exporter
**Problem:** The nginx access log was writing in the default `main` format (no `$request_time`), so the Python exporter regex could not parse any lines. Zero metrics were collected.
**Root cause:** The Dockerfile was copying `nginx.conf` to `/etc/nginx/conf.d/default.conf`, but the container was still using the default `nginx.conf` `main` log format because the `log_format prometheus_format` definition was not being picked up.
**Fix:** Updated `nginx.conf` to define `prometheus_format` with `rt=$request_time` at the http block level and set `access_log` to use it inside the server block. Rebuilt and pushed the Docker image.
**Lesson:** Always verify actual log output with `kubectl exec` before assuming config changes are live. A rebuilt image is required for nginx config changes.

---

## 3. Prometheus Operator Incompatibility with Prometheus v3.x
**Problem:** kube-prometheus-stack 56.6.2 ships with Prometheus operator v0.71.2 which only supports Prometheus v2.x. Prometheus v3.12.0 was installed, causing the operator to fail with `unsupported Prometheus major version` and stop reconciling ServiceMonitors entirely.
**Fix:** Pinned Prometheus back to v2.51.0 by adding `image.tag: v2.51.0` under `prometheusSpec` in `monitoring/values.yaml` and re-ran helm upgrade with `--version 56.6.2`.
**Lesson:** Always pin chart and image versions together. A mismatch between operator and application versions silently breaks reconciliation.

---

## 4. ServiceMonitor Port Name Mismatches
**Problem:** The nginx-exporter container port was named `metrics` in `deployment.yaml` but the service `targetPort` was `nginx-metrics` and the ServiceMonitor endpoint was `port: nginx-metrics`. The names did not match end-to-end, so Prometheus discovered but dropped all targets.
**Fix:** Standardised the port name to `metrics` across `deployment.yaml`, `service.yaml`, and `servicemonitor.yaml`. The service `name` field must match what the ServiceMonitor `port` field references.
**Lesson:** The ServiceMonitor `port` field matches against the **service port name**, not the container port name or targetPort. All three files must use consistent names.

---

## 5. Splitting Single ServiceMonitor into Two
**Problem:** kube-prometheus-stack 56.6.2 only created one scrape pool (`portfolio/0`) even when the ServiceMonitor had two endpoints defined. The second endpoint (app-metrics) was never scraped.
**Fix:** Split into two separate ServiceMonitor resources — `portfolio-nginx` and `portfolio-app` — each with a single endpoint.
**Lesson:** Older versions of the Prometheus operator have a bug where multiple endpoints in a single ServiceMonitor only generate one scrape pool. Splitting into separate ServiceMonitors is a reliable workaround.

---

## 6. RBAC for GitHub Actions Service Account
**Problem:** Helm upgrade failed with `servicemonitors.monitoring.coreos.com is forbidden` — the GitHub Actions service account did not have permission to manage ServiceMonitor custom resources.
**Fix:** Added the `monitoring.coreos.com` API group with full ServiceMonitor permissions to the ClusterRole. Moved RBAC from CLI-only to a `k8s/rbac.yaml` file in the repo, applied via a GitHub Actions step before the Helm upgrade.
**Lesson:** When adding new CRDs (like ServiceMonitors), always update the service account's ClusterRole. Version-controlling RBAC in the repo prevents drift.

---

## 7. Traefik Port Conflict Blocking Node Exporter Scheduling
**Problem:** The node exporter DaemonSet could not schedule on the control node because Traefik was bound to port 9100 (its metrics entrypoint), which node exporter also requires as a host port.
**Root cause:** Traefik was configured with `--entryPoints.metrics.address=:9100/tcp` from its Helm installation.
**Fix:** Moved Traefik metrics to port 9101 using helm upgrade. Deleted the pending node exporter pod so it rescheduled successfully.
**Lesson:** Node exporter requires host port 9100. Any other process on the node using that port will block the DaemonSet from scheduling.

---

## 8. Recovering from Broken Traefik Installation
**Problem:** Running `helm upgrade traefik` via CLI conflicted with K3s's internal HelmChart CRD management. K3s manages Traefik via its own helm-install jobs, and the CLI upgrade left behind CRDs without the correct Helm ownership labels, causing K3s's reinstall jobs to fail with `invalid ownership metadata`.
**Fix:** Added the required `app.kubernetes.io/managed-by=Helm` label and `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace` annotations to all Traefik CRDs, then deleted the stuck jobs so K3s could retry. Restarted K3s with `sudo systemctl restart k3s`.
**Lesson:** Never use `helm upgrade` via CLI on components K3s manages internally (Traefik, CoreDNS). Use K3s HelmChart resources or HelmChartConfig instead.

---

## 9. Port-Forward Script Not Restarting on Connection Drop
**Problem:** The systemd port-forward service started all port-forwards on boot but did not restart individual ones when connections dropped (e.g. after a Helm deploy replaced pods).
**Fix:** Rewrote the script with a `forward()` function that wraps each `kubectl port-forward` in a `while true` loop with a 5-second sleep on failure, so each port-forward restarts independently on connection loss.
**Lesson:** `kubectl port-forward` drops when the target pod is replaced. Any long-running port-forward setup needs auto-restart logic.

---

## 10. Grafana Account Lockout from Provisioning Sidecar
**Problem:** Grafana's internal provisioning sidecar was hitting the API with wrong credentials repeatedly, locking the admin account within minutes of pod startup.
**Root cause:** The Grafana PVC persisted a SQLite database with a different password than what was in the `grafana-admin-secret`, causing a mismatch between the stored password and the secret.
**Fix:** Deleted the Grafana PVC to clear the persisted database, recreated the secret with a known password, and re-ran helm upgrade to let Grafana initialise fresh from the secret.
**Lesson:** When `existingSecret` is configured for Grafana, the PVC-persisted database must match. If they diverge, delete the PVC and let Grafana reinitialise.

---

## 11. PrometheusRule Metric Name Errors
**Problem:** The `DeploymentReplicasMismatch` alert used `kube_deployment_status_available_replicas` which does not exist. The correct metric is `kube_deployment_status_replicas_available`.
**Fix:** Corrected the metric name in the PrometheusRule. Always verify metric names exist by querying Prometheus directly before writing alert expressions.

**Problem:** The `PodNotReady` alert fired for completed Helm install job pods because `kube_pod_status_ready{condition="true"} == 0` matches any pod not in ready state, including intentionally completed jobs.
**Fix:** Updated the expression to exclude job-owned pods using `kube_pod_owner{owner_kind!="Job"}`.

---

## 12. Python Metrics Exporter Regex Named Group Error
**Problem:** The exporter failed to start with `re.error: unknown extension ?P\S` — named capture groups in the LOG_PATTERN regex had their angle brackets stripped, turning `(?P<name>\S+)` into `(?P\S+)`.
**Fix:** Restored the correct named group syntax with angle brackets in all capture groups.
**Lesson:** Always test regex patterns before building the Docker image. A syntax error in a compiled pattern crashes the exporter on startup.

---

## 13. Docker Image Not Updating Despite Code Changes
**Problem:** Pods continued running old nginx config even after `nginx.conf` was updated and pushed. The image tag was `:latest` with `pullPolicy: IfNotPresent`, so Kubernetes reused the cached image.
**Fix:** GitHub Actions deploys use SHA-based tags (`sha-xxxxxxx`) so each commit produces a unique tag that Kubernetes always pulls fresh. For the `latest` tag, temporarily set `pullPolicy: Always` to force a fresh pull.
**Lesson:** Never rely on `latest` with `IfNotPresent` pull policy for active development. SHA-based tags with `IfNotPresent` is the correct pattern.

---

## 14. Grafdata Data Gap After Pod Restart
**Problem:** Grafana dashboards showed a data gap for several hours.
**Root cause:** Not a connectivity issue — Grafana already talked to Prometheus via internal cluster DNS. The gap was caused by Grafana itself being down during PVC recovery, not by SSH tunnel drops.
**Lesson:** Always distinguish between Grafana being down (data collection continues in Prometheus but dashboards are unavailable) versus Prometheus being down (data is actually lost). Check pod restart timestamps against the gap period.

---

## Key Commands Reference

```bash
# Check why a pod is pending
kubectl describe pod -n <namespace> <pod-name> | grep -A20 "Events:"

# Check port usage on node
sudo ss -tlnp | grep <port>

# Force Prometheus to reload rules
kubectl rollout restart statefulset -n monitoring prometheus-kube-prometheus-stack-prometheus

# Check Prometheus scrape targets
curl -s "http://localhost:9090/api/v1/targets?scrapePool=<pool-name>" | python3 -m json.tool

# Check what metrics exist
curl -s "http://localhost:9090/api/v1/label/__name__/values" | python3 -m json.tool | grep <pattern>

# Fix kubeconfig permissions after k3s restart
sudo chmod 644 /etc/rancher/k3s/k3s.yaml

# Check Prometheus operator logs
kubectl logs -n monitoring <operator-pod-name> --tail=30 | grep -i "error"

# Verify nginx config is correct in running pod
kubectl exec -n portfolio <pod-name> -- cat /etc/nginx/conf.d/default.conf

# Check actual log format being written
kubectl exec -n portfolio <pod-name> -- tail -5 /var/log/nginx/access.log
```
