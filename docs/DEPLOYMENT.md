# Deployment runbook (Azure Container Apps)

The public demo runs on Azure Container Apps, mirroring the stack of the lab's example PoC.
State below was verified live against the running deployment on **2026-08-11**.

Live URL: `https://claims-desk.graybush-6924b6da.germanywestcentral.azurecontainerapps.io`

## What is deployed

| | |
|---|---|
| Subscription | the KIT **student** subscription (tenant `student.kit.edu`) |
| Resource group | `rg-claims-desk`, region `germanywestcentral` |
| Registry | `claimsdeskacryeiu` (ACR Basic, admin user enabled) |
| Container Apps env | `claims-desk-env` |
| Container app | `claims-desk`, 0.5 vCPU / 1Gi, `minReplicas = maxReplicas = 1` |
| Current image | `claimsdeskacryeiu.azurecr.io/claims-desk:v5` |
| Secrets | `openai-key`, `demo-password` (plus the auto-created ACR pull secret) |

`minReplicas = 1` is deliberate: it costs a little to keep warm and removes cold starts,
which matters when the app is opened live in a call.

## Two constraints worth knowing before you start

1. **Select the right tenant.** `az login` may default to a guest subscription from another
   tenant. Confirm before every deployment command:

   ```bash
   az account show --query "{sub:name, tenant:tenantDefaultDomain, user:user.name}" -o table
   ```

   If it is not the student tenant, `az login --tenant <student-tenant-domain>` and
   `az account set --subscription "<name>"`.

2. **ACR Tasks are unavailable on this subscription**, so `az acr build` fails. Build the
   image locally and `docker push` instead. Every step below assumes that.

## Redeploy a new image

Bump the tag on every push. Container Apps will not reliably pick up a re-pushed identical
tag, and a monotonic tag keeps the revision history readable.

```bash
az acr login --name claimsdeskacryeiu
docker build -t claimsdeskacryeiu.azurecr.io/claims-desk:v6 .
docker push claimsdeskacryeiu.azurecr.io/claims-desk:v6
az containerapp update -n claims-desk -g rg-claims-desk \
  --image claimsdeskacryeiu.azurecr.io/claims-desk:v6
```

Then confirm the new revision is the one serving traffic:

```bash
az containerapp revision list -n claims-desk -g rg-claims-desk \
  --query "[].{name:name, active:properties.active, traffic:properties.trafficWeight, image:properties.template.containers[0].image}" -o table
```

## Rotate a secret

Secrets are stored as Container Apps secrets and injected as environment variables. Never
put either value in the repo, in a Dockerfile, or in a commit message.

```bash
az containerapp secret set -n claims-desk -g rg-claims-desk \
  --secrets openai-key=<new-kit-toolbox-key>
az containerapp update -n claims-desk -g rg-claims-desk   # restart to pick it up
```

The same pattern applies to `demo-password`. The demo password ships with the application
materials, not with this repository.

## Check health and logs

```bash
curl -s https://claims-desk.graybush-6924b6da.germanywestcentral.azurecontainerapps.io/api/health
az containerapp logs show -n claims-desk -g rg-claims-desk --tail 100
```

`/api/health` is outside the password gate and reports the event count, the default model,
whether the gate is on, and whether an API key is present. It does not reveal either value.

## Recreate from scratch

Only needed after a teardown. The registry name must be globally unique, so pick a new
suffix rather than reusing `claimsdeskacryeiu`.

```bash
az group create -n rg-claims-desk -l germanywestcentral
az acr create -n <newuniquename> -g rg-claims-desk --sku Basic --admin-enabled true
az containerapp env create -n claims-desk-env -g rg-claims-desk -l germanywestcentral
# build + push the image as above, then:
az containerapp create -n claims-desk -g rg-claims-desk --environment claims-desk-env \
  --image <newuniquename>.azurecr.io/claims-desk:v1 \
  --registry-server <newuniquename>.azurecr.io \
  --target-port 8000 --ingress external \
  --cpu 0.5 --memory 1Gi --min-replicas 1 --max-replicas 1 \
  --secrets openai-key=<key> demo-password=<password> \
  --env-vars OPENAI_API_KEY=secretref:openai-key DEMO_PASSWORD=secretref:demo-password
```

The FQDN is assigned by Azure and will differ from the one above. Update the URL in
`README.md` and `CLAUDE.md` if it changes.

## Teardown

One command removes everything, including the registry and all images:

```bash
az group delete --name rg-claims-desk
```

Running cost is roughly EUR 15 to 25 per month while the app is up, dominated by the
always-on single replica. Tear it down once the demo is no longer needed.
