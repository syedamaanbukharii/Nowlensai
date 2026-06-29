# Kubernetes deployment

Cloud-agnostic manifests for the NowLens API and frontend. The same manifests
run on AWS (EKS), Azure (AKS), GCP (GKE), or any conformant cluster — only the
backing-service endpoints, ingress class, and image registry differ, and those
are all configuration (ConfigMap / Secret / kustomize), never code.

## What's here

| File | Purpose |
|---|---|
| `namespace.yaml` | `nowlens` namespace |
| `configmap.yaml` | Non-secret config (env, service endpoints, pool sizes) |
| `secret.example.yaml` | **Template** for the Secret (JWT secret, DB URL, API keys) |
| `migrate-job.yaml` | Runs `alembic upgrade head` + `nowlens bootstrap` (idempotent) |
| `api-deployment.yaml` / `api-service.yaml` | API Deployment (probes, non-root, HPA target) + ClusterIP |
| `frontend-deployment.yaml` / `frontend-service.yaml` | Next.js standalone Deployment + ClusterIP |
| `hpa.yaml` | CPU-based autoscaling for the API |
| `ingress.yaml` | Routes the host to frontend + API surface |
| `kustomization.yaml` | Base; `kubectl apply -k k8s/` |

## Backing services

Postgres, Qdrant, and Redis are treated as **external** dependencies (managed
services or separately-deployed charts), referenced only by URL in the ConfigMap
/ Secret. This keeps the application cloud-portable: point the URLs at RDS /
Cloud SQL / Azure Database, Elasticache / Memorystore, and managed or
self-hosted Qdrant as appropriate.

## Deploy

```bash
# 1. Build + push images to your registry, then set them (or edit kustomization.yaml):
#    docker build -t <registry>/nowlens-api:<tag> .
#    docker build -t <registry>/nowlens-frontend:<tag> \
#      --build-arg NEXT_PUBLIC_API_BASE_URL=https://nowlens.example.com ./frontend

# 2. Create the namespace and the Secret (never commit real secrets):
kubectl apply -f k8s/namespace.yaml
kubectl -n nowlens create secret generic nowlens-secrets \
  --from-literal=NOWLENS_SECURITY__JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  --from-literal=NOWLENS_DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/nowlens"

# 3. Review configmap.yaml + ingress host, then apply everything:
kubectl apply -k k8s/

# 4. Wait for the migration Job, then the rollout:
kubectl -n nowlens wait --for=condition=complete job/nowlens-migrate --timeout=300s
kubectl -n nowlens rollout status deploy/nowlens-api
```

## Notes

- **Production secret guard.** The API refuses to start unless
  `NOWLENS_SECURITY__JWT_SECRET` is a strong (>=32 char) secret.
- **Frontend API URL is build-time.** `NEXT_PUBLIC_API_BASE_URL` is inlined when
  the image is built (Next.js limitation), so rebuild the frontend image per
  environment — or serve the frontend from Vercel and run only the API here.
- **Secret management.** Prefer External Secrets / Sealed Secrets / a CSI secret
  store over a literal Secret in production.
- **Existing Qdrant data.** If upgrading a cluster that already has indexed
  vectors from before multi-tenancy, re-ingest so chunks carry a `tenant_id`
  payload (tenant-filtered search excludes vectors without it).
