# Approve or block AI agent tool calls with Atryum

Put a governance gateway between AI agents and their tools: every action is approved, denied, or escalated against each agent's charter, with full audit.

## Table of Contents

- [Overview](#overview)
- [Detailed description](#detailed-description)
  - [Architecture diagrams](#architecture-diagrams)
- [Requirements](#requirements)
  - [Minimum hardware requirements](#minimum-hardware-requirements)
  - [Minimum software requirements](#minimum-software-requirements)
  - [Required user permissions](#required-user-permissions)
- [Deploy](#deploy)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Validating the deployment](#validating-the-deployment)
  - [Walkthrough](#walkthrough)
  - [Delete](#delete)
- [Repository structure](#repository-structure)
- [References](#references)
- [Technical details](#technical-details)
- [Tags](#tags)

## Overview

Agents use *tools* to take action in the real world: paying invoices, placing trades, erasing customer data. [Atryum](https://atryum.org) intercepts every one of those tool calls **before it executes** and decides — automatically, via an AI judge, or by escalating to a human — whether it should be allowed. This quickstart deploys Atryum on OpenShift together with six demo agents from financial services and GDPR compliance, pre-seeded with governance charters and rules, so you can watch an agent get confused and see the gateway contain the damage.

## Detailed description

Financial institutions want the productivity of agentic AI — an accounts-payable agent that pays invoices, a portfolio agent that rebalances funds, a servicing agent that resolves disputes. The failure mode isn't a reckless agent; it's a helpful one. Picture a revenue-ops manager asking their assistant to "send the account summary to the customer": the agent over-collects to be thorough, attaches a broad export, and a permitted email quietly carries 1,200 other customers' records out the door. Nothing crashed. Policy documents and system prompts didn't stop it — the agent can ignore them, and nothing along the way inspected what the call actually carried.

This quickstart demonstrates enforcement at the only place it cannot be bypassed: the tool boundary. Atryum sits inline between each agent and its tools, and every tool call is checked against policy *before it executes*. Two decision layers do the work: **static rules** — deterministic access-control lists that auto-approve, auto-deny, or forward each operation, resolving the easy calls in about a millisecond — and **AI evaluation**, where an independent LLM judge reads the call (arguments included) against that agent's *charter*, a plain-language constitution of what it may and may not do, returning a decision with its confidence and reasoning. Anything unmatched is held for a human: the call pauses, not the platform. Every decision lands in a durable audit log.

The included demo makes this concrete. Three finance agents (treasury disbursement, portfolio rebalancing, customer servicing) and three GDPR data-subject-rights agents run against mock backends. The agents are deliberately naive — they attempt every action and let the gateway decide. Across one run you'll see the full spectrum of outcomes: a $240 invoice to a verified payee is **auto-approved** by a static rule, a routine disbursement is **AI-approved** against the treasury charter, a large payment is held for **human approval**, and a payment to a sanctioned account — or an erasure request under legal hold — is **denied** with the judge's reasoning attached.

### Architecture diagrams

![Architecture diagram: the user runs demo agents from a dashboard; the agents' tool calls flow through the Atryum gateway, which resolves each one via static rules, AI evaluation against the agent's charter, or human approval before it reaches the demo backends; a Helm post-install job seeds agents, charters, and rules, PostgreSQL stores the durable audit log, and one LLM endpoint powers both the judge and the agents](docs/images/architecture.svg)

Atryum sits inline between the agents and the tools they call — every tool call is checked against policy before it executes, resolved by static rules or judged by an AI evaluation against the agent's charter, with human approval as the fallback. One Helm release deploys the whole loop: Atryum (with PostgreSQL for rules, charters, and the audit log), the demo agents container, and a post-install Job that seeds the MCP servers, the six agents with their charters, the rule tiers, and the judge's LLM configuration through Atryum's REST API. One user-supplied LLM credential powers both the judge and the demo agents.

## Requirements

### Minimum hardware requirements

No GPU is required — the LLM is consumed as a service (OpenAI or any OpenAI-compatible endpoint).

**Total for the quickstart (3 pods + a short-lived seed Job):**
- CPU: 0.5 vCPU (requests) / ~2 vCPU burst
- Memory: 1 GiB (requests) / 2 GiB (limits)
- Storage: 10 GiB PersistentVolume (PostgreSQL)

### Minimum software requirements

- OpenShift 4.14 or later (any cluster with the Route API and a default StorageClass)
- No OpenShift AI dependency — optional: point `model.endpoint` at an OpenShift AI model server instead of OpenAI
- `oc` CLI 4.14+, `helm` 3.12+, `make`

### Required user permissions

Any user who can:
- create a project/namespace (or be given one)
- deploy applications via Helm (Deployments, Services, Secrets, ConfigMaps, Jobs, PVCs, Routes)

No cluster admin access is required. (The Makefile auto-detects the cluster's apps domain via `oc get ingresses.config/cluster`, which most users can read; if not, Routes still work with auto-assigned hosts.)

## Deploy

### Prerequisites

Before deploying, ensure you have:
- Access to an OpenShift cluster, with `oc` logged in
- `helm` and `make` installed
- An **LLM API key** — OpenAI, or any OpenAI-compatible endpoint (MaaS, vLLM, an OpenShift AI model server). One key powers both Atryum's AI-evaluation judge and the demo agents.

### Installation

1. Clone the repository:
```bash
git clone https://github.com/rh-ai-quickstart/approve-agent-tools-with-atryum.git
cd approve-agent-tools-with-atryum
```

2. Configure your LLM credential:
```bash
make env-init          # creates .env
# edit .env: set MODEL_API_KEY (and MODEL_NAME/MODEL_ENDPOINT for non-OpenAI endpoints)
```

3. Install (creates the project, deploys Atryum + demo, seeds agents/charters/rules, prints the URLs):
```bash
make install
```

Defaults: project `atryum-quickstart`, release `quickstart` — override like `make install NAMESPACE=my-project`.

<details>
<summary>Prefer plain Helm? (what the Makefile runs)</summary>

```bash
PROJECT="atryum-quickstart"
oc new-project ${PROJECT}
helm install quickstart ./chart --namespace ${PROJECT} \
  --set model.api_key=YOUR_API_KEY \
  --set model.name=YOUR_MODEL_NAME \
  --set model.endpoint=YOUR_MODEL_ENDPOINT \
  --set clusterDomain=$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')
```

> **Note**: `model.endpoint` is the base URL **without** the `/v1` suffix (e.g. `https://my-maas-instance:443`). Leave `model.endpoint` empty to use OpenAI directly.

</details>

#### Testing model access (before deploying)

You can verify your endpoint is reachable **before** installing the chart:

```bash
oc run test-model-access --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  -- /bin/sh -c 'curl -sf --max-time 10 \
    -H "Authorization: Bearer YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"YOUR_MODEL_NAME\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one word.\"}], \"max_tokens\": 10}" \
    "YOUR_MODEL_ENDPOINT/v1/chat/completions" && echo "" && echo "SUCCESS" || echo "FAILED"'
```

The same check ships as a Helm test: `helm test quickstart --namespace atryum-quickstart` (runs when `model.endpoint` is set).

### Validating the deployment

1. Check all pods are running and the seed Job completed:
```bash
make status        # or: oc get pods,jobs,routes -n atryum-quickstart
```
Expected: `quickstart-atryum`, `quickstart-postgres`, and `quickstart-demos` pods `Running`; job `quickstart-configure` `Complete`.

2. Get the URLs:
```bash
make urls
```

3. See what the seeding Job configured (servers, 6 agents + charters, 5 rules, judge):
```bash
make logs-configure
```

### Walkthrough

1. Open the **demo dashboard** URL, pick the **AP / Treasury Disbursement Agent**, and run it.
2. The agent tries to pay every pending invoice. Watch the stream span all four outcomes: reads are **auto-approved** by static rules; small payments to verified payees are **AI-approved** against the agent's charter; large payments are held for **human approval**; payments to sanctioned accounts are **denied**.
3. Open the **Atryum UI** → **Invocations** to see every decision with its confidence and reasoning; approve or deny anything held for a human, then re-run the agent.
4. **Rules** shows the seeded tiers; **Agents** shows each agent's charter — the plain-language constitution the judge enforces. Edit a charter and re-run to see decisions change.
5. Try the GDPR demo at the dashboard's `/gdpr` path: erasure under legal hold gets denied, consent withdrawal sails through.
6. `make configure` re-applies the original seed at any time (idempotent).

### Delete

1. Uninstall the Helm release (keeps the namespace and the PostgreSQL PVC):
```bash
make uninstall
```

2. Delete the whole project including data:
```bash
make cleanup-namespace     # or: oc delete project atryum-quickstart
```

## Repository structure

```
.
├── Makefile                  # Entrypoint: make install / configure / status / uninstall
├── .env.example              # MODEL_API_KEY, MODEL_NAME, MODEL_ENDPOINT
├── quickstart.yaml           # Publication metadata
├── chart/                    # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml           # model.*, atryum, postgres, demo, configure
│   ├── templates/            # Atryum, PostgreSQL, demo, Routes, seed Job, helm test
│   └── files/
│       ├── seed.json         # 6 agents + charters, MCP servers, rule tiers
│       └── configure.py      # Idempotent seeding via Atryum's REST API
├── docs/images/              # Architecture diagram
└── README.md
```

The demo agents' source lives in its own repository and ships as the [`validmind/atryum-finance-demo`](https://hub.docker.com/r/validmind/atryum-finance-demo) image.

## References

- [Atryum documentation](https://atryum.org)
- [Atryum source](https://github.com/validmind/atryum)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
- [ValidMind Agent Authority](https://validmind.com) — open-source Atryum deployed inside ValidMind, wired to the model/agent inventory, hierarchical charters, and evidence systems that make every decision audit-ready (not required by this quickstart)

## Technical details

- **Integration mode**: this quickstart uses Atryum as an **MCP proxy** — one of its three integration modes (MCP proxy, harness permission check, orchestration control). The demo agents connect to `/mcp/finance` and `/mcp/gdpr` with an `agent_id` that resolves their Atryum agent record; Atryum forwards `tools/list` transparently and intercepts every `tools/call`.
- **Decision layers, as seeded** (first match wins): **static rules** auto-approve read-only tools in-process (~1 ms, no model call) → **AI evaluation** judges state-changing tools against the calling agent's charter, returning a decision with confidence and reasoning → a blanket **human approval** fallback holds anything unmatched. AI evaluation **fails closed** to human approval if the judge LLM is unreachable. A judge check runs alongside a multi-second agent reasoning turn, so the overhead is a fraction of a step the loop already pays for.
- **Latency**: the vast majority of calls resolve on the static-rule path with no model call; only forwarded calls pay for the judge.
- **Charters** come from a ValidMind AI-governance organization template (the same text a governed org would sync from ValidMind); here they're seeded directly onto Atryum agent records, so no ValidMind connection is needed.
- **Seeding** is a Helm post-install/post-upgrade hook Job driving Atryum's REST API (`/api/v1/servers`, `/api/v1/agents`, `/api/v1/rules`, `/api/v1/llm-configs`) — idempotent, stdlib-Python only.
- **Auth**: Atryum runs in no-auth quickstart mode (no `[[auth]]` blocks): its UI and operator API are unprotected behind the Route. Intentional for a demo cluster — add auth before exposing further.
- **Images**: `validmind/atryum` (gateway) and `validmind/atryum-finance-demo` (dashboard :8000, mock MCP backends :8001); both run under OpenShift's arbitrary UIDs. PostgreSQL is `quay.io/sclorg/postgresql-16-c9s`.

## Tags

**Title:** Approve or block AI agent tool calls with Atryum
**Description:** Put a governance gateway between AI agents and their tools: every action is approved, denied, or escalated against each agent's charter, with full audit.
**Industry:** Financial Services
**Product:** OpenShift
**Use case:** Security, governance, compliance
**Partner:** ValidMind
**Contributor org:** ValidMind
