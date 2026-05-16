# Azure ML GPU Quota Request — paper trail

Submitted: 2026-05-16
Subscription: `4ea8ab04-9d53-46cf-9d80-de7d625ba88a` (Crowe Mycology LLC)
Workspace: `crowelm-mlws-eastus2` in eastus2
Resource group: `rg-crowelm-prod`

## Current state

```
$ az vm list-usage -l eastus2 | grep -E "NC|ND|NV"  (positive limits only)
internalNDMSv1Family   0/65   ← Microsoft-internal preview family (SKU name not exposed)

All other GPU families: 0/0
  standardNCFamily, standardNCSv3Family
  StandardNCADSA10v4Family, Standard NCASv3_T4 Family
  StandardNCADSA100v4Family, StandardNCadsH100v5Family
  standardNDSH100v5Family, standardNDISRH200V5Family
  standardNVADSA10v5Family
```

The workspace exists, the storage account is provisioned, and `submit_azure_ml.py`
fails at `ClusterMinNodesExceedCoreQuota` because every customer-facing GPU family
has a 0-core quota.

## What to request

Pick **one** of these (Microsoft typically approves the cheaper request faster):

| Family | SKU | Use case | Cores requested |
|---|---|---|---|
| **NCadsT4_v3** | `Standard_NC4as_T4_v3` | Cheap LoRA fine-tune (T4 16GB) | **24 cores** (1 node × 4 vCPU + headroom for retries) |
| NCadsA100_v4 | `Standard_NC24ads_A100_v4` | Fast LoRA, large context (A100 80GB) | 48 cores |
| NCadsH100_v5 | `Standard_NC40ads_H100_v5` | Fastest single-GPU (H100 80GB) | 80 cores |

Recommendation: request **24 cores on NCadsT4_v3** — covers the immediate LoRA
training run on the smallest viable GPU. A100/H100 quotas can be requested
separately later for production-scale training.

## How to file (Portal — fastest path)

1. Sign in to https://portal.azure.com as `mike@southwestmushrooms.com`.
2. Search "Quotas" → choose **Compute** provider.
3. Filter by subscription `Crowe Mycology LLC` and location `East US 2`.
4. Find the row labeled "Standard NCASv3_T4 Family vCPUs" (or "NCadsA100v4
   Family vCPUs" for the A100 path).
5. Click the pencil icon → "New limit": `24` (or `48` for A100).
6. Justification (paste this):

> Crowe Mycology LLC operates the `crowelm-mlws-eastus2` workspace for
> AI/ML training workloads. We need 24 vCPU on the NCASv3_T4 family to
> run LoRA fine-tuning jobs on Gemma 4 and similar 4B-8B parameter
> models for the Gemma 4 Good Hackathon submission. Single-node,
> short-duration (≈3-hour) jobs. The compute cluster is configured for
> auto-scale-down to zero between jobs.

7. Submit. Typical approval: 1-3 business days for T4, longer for A100/H100.

## How to file (CLI — non-interactive variant)

```bash
az support tickets create \
  --ticket-name "T4 quota for crowelm-mlws" \
  --title "Increase NCASv3_T4 Family vCPUs to 24 in eastus2" \
  --description "$(cat <<'EOF'
Crowe Mycology LLC requests 24 vCPU of Standard NCASv3_T4 family quota
in East US 2 for the crowelm-mlws-eastus2 workspace. LoRA fine-tuning
of Gemma 4 E4B for the Gemma 4 Good Hackathon. Auto-scale cluster
(min=0, max=1, idle_time=120s). Estimated monthly spend: low single
digits.
EOF
)" \
  --severity moderate \
  --problem-classification "/providers/Microsoft.Support/services/quota_service_guid/problemClassifications/cores_quota_classification_guid" \
  --contact-first-name "Michael" \
  --contact-last-name "Crowe" \
  --contact-method email \
  --contact-email mike@southwestmushrooms.com \
  --contact-country US \
  --contact-language en-US \
  --contact-timezone "Pacific Standard Time"
```

(The classification GUIDs are environment-specific — discover with
`az support services list` and `az support services problem-classifications list`.)

## Status

- 2026-05-16: filed via portal (TODO: paste ticket # here once submitted)
- TODO: rerun `python scripts/submit_azure_ml.py --gpu t4` once approved
