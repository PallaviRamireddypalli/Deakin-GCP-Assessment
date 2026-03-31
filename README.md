# GCP Guardrail Control Plane

A policy driven, event driven, low cost GCP guardrail system for detecting and mitigating risky notebook runtime usage across shared cloud environments.

This repository contains:

- the core policy engine
- the native GCP adapters
- the serverless deployment entrypoint
- the local test suite
- the live validation utilities
- the technical solution artifacts

The design is intentionally built to be:

- simple to understand
- safe by default
- scalable across many projects
- adaptable to multiple use cases
- easy for a reviewer to run locally and validate in GCP

---

## 1. Problem statement

This solution protects GCP projects from risky runtime behavior such as:

- unapproved high cost GPU or CPU usage
- idle notebook runtimes burning project budget
- project usage outside allowed baseline constraints
- runtime usage that exceeds project scope unless approved by exception
- repeated critical incidents that require escalation

It was designed around a university style multi project environment where projects may be created and managed dynamically, and where one user can accidentally consume a monthly budget by attaching an expensive runtime and leaving it idle.

---

## 2. Key requirements addressed

### Explicit requirements
- fully automated detection and mitigation
- protection against unplanned high cost runtime usage
- automatic onboarding and offboarding
- support for 1:1 and 1:many principal models
- applicability across PhD Research, Teaching and Learning, Research, and Professional Staff
- scalability to a large multi project environment
- upgradeability within a two week maintenance window
- low annual control plane cost target under A$1000
- native GCP implementation path

### Implicit requirements
- no billing shock by design
- centralized shared control plane rather than per project infrastructure
- safe dry run defaults for destructive actions
- persistent state across runs for repeated incident handling
- reproducibility with local tests and live GCP verification
- clear separation between policy logic and cloud adapters
- no blind spots caused by manual project registration
- simple operational model that is easy to support and extend

---

## 3. Solution summary

The design uses a shared serverless guardrail control plane instead of deploying separate infrastructure per project.

The system evaluates:

- requested resources before or at provisioning time
- running resources during periodic sweeps or event driven checks

It then decides whether to:

- allow
- deny
- notify
- stop
- escalate

The implementation keeps the core logic stable and moves cloud specific behavior into adapters. That makes the system easier to test locally and easier to extend in GCP.

---

## 4. High level architecture

### Native GCP services used
- Cloud Logging sink
- Pub/Sub
- Cloud Run function style serverless entrypoint
- Cloud Scheduler
- Firestore
- Cloud Resource Manager
- Notebook Runtime / Colab Enterprise API
- IAM service accounts

### Logical flow

1. Cloud Audit Logs generate admin activity events when users change resources.
2. Logging sink exports relevant audit log events to a shared Pub/Sub topic.
3. Cloud Scheduler publishes periodic sweep messages to the same Pub/Sub topic.
4. Pub/Sub acts as the shared event bus for real time events and scheduled sweeps.
5. Cloud Run serverless function receives events, parses payloads, runs the orchestrator, and invokes mitigation adapters.
6. Firestore stores managed project registry state and runtime state across runs.
7. Cloud Resource Manager provides live project discovery.
8. Notebook Runtime adapter performs runtime mitigation in dry run mode by default, and can be switched to real stop mode explicitly.

> The high level architecture intentionally hides platform plumbing details and focuses on the core relevant services only.

---

## 5. Architecture design principles

### 5.1 Stable core, replaceable adapters
The solution separates:

- core domain logic
- cloud adapters
- deployment entrypoint

This keeps the policy engine testable locally while allowing progressive GCP integration.

### 5.2 Safe by default
The repository defaults to:

- dry run runtime mitigation
- no destructive stop unless explicitly enabled
- centralized low cost services only
- no per project infrastructure sprawl

### 5.3 Shared control plane
This is one shared control plane for many projects, not one deployment per project.

That means:
- one shared Pub/Sub topic
- one shared serverless function
- one shared Firestore store
- one shared scheduler job
- dynamic project discovery and evaluation

---

## 6. Automatic onboarding and offboarding

The control plane automatically manages project lifecycle participation instead of relying on manual registration.

### Onboarding
- governed projects are discovered dynamically from GCP using Cloud Resource Manager
- newly discovered in scope projects are automatically added to the managed project registry
- project governance metadata is merged into the internal policy model before evaluation

### Offboarding
- projects that are no longer in scope or no longer active can be removed from the managed registry automatically
- this prevents stale governance state and reduces manual maintenance

### Why this matters
This design avoids blind spots in the project hierarchy and supports a growing estate without requiring manual setup for every project.

---

## 7. Scalability model

This solution is designed to scale to a large project estate without one deployment per project.

### Why it scales
- one shared control plane
- no per project scheduler job
- no per project serverless service
- no per project database
- policy engine evaluates projects dynamically
- onboarding and offboarding are data driven
- event driven compute means no always on orchestration layer

### 1600 project fit
The scaling unit is:
- event throughput
- periodic batch evaluation
- Firestore document volume

It is not the number of deployed services.

### Operational simplicity
Because the design uses centralized shared services, the number of projects does not linearly increase the number of control plane components.

---

## 8. Upgradeability within two weeks

The solution is designed to be upgradeable within a short maintenance window because:

- policy rules are isolated in the core engine
- adapters are separate from domain logic
- deployment entrypoint is thin
- infrastructure footprint is centralized and small
- dry run flags allow safe rollout of new mitigation behavior

### Typical upgrade categories
- change threshold or policy rules
- add a new approval rule
- extend runtime parsing
- replace a dry run adapter with a real action adapter
- add new event filters
- update IAM or deployment settings

This makes short upgrade windows practical and low risk.

---

## 9. Cost control and no billing shock design

This project intentionally avoids expensive or operationally heavy services in the MVP.

### Cost control choices
- serverless only
- shared services only
- no always on VM control plane
- no per project deployments
- Firestore for lightweight state
- Pub/Sub for event fan in
- Cloud Scheduler with modest cadence
- dry run runtime stop by default
- project budget alerts configured separately

### Why this stays under A$1000 per year
The control plane is intentionally lightweight because:
- compute runs only on events or scheduled sweeps
- there is one shared function, not 1600 functions
- Firestore usage is small for state storage
- Pub/Sub traffic is low relative to typical quotas
- there is no analytics or dashboarding stack in the MVP
- there are no always on resources

### Reviewer safety
The repository is safe to review because:
- runtime mitigation defaults to dry run
- no destructive action happens unless explicitly enabled
- infrastructure is minimal
- no high cost workloads are created by default

---

## 10. Repository structure

```text
.
├── src/
│   ├── actions.py
│   ├── approvals.py
│   ├── budgets.py
│   ├── colab_runtime_controller.py
│   ├── engine.py
│   ├── firestore_state_store.py
│   ├── gcp_project_discovery.py
│   ├── local_adapters.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── policy.py
│   ├── ports.py
│   ├── registry.py
│   ├── simulator.py
│   ├── state.py
│   └── live_*_demo.py
├── tests/
├── data/
│   ├── scenario_student_a.json
│   ├── scenario_edge_cases.json
│   ├── runtime_stop_test.json
│   └── project_profiles.example.json
├── docs/
│   ├── architecture_diagram.png
│   └── solution_document.pdf
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

### Production path
These files make up the main production implementation:

- `main.py`
- `src/orchestrator.py`
- `src/engine.py`
- `src/policy.py`
- `src/actions.py`
- `src/gcp_project_discovery.py`
- `src/firestore_state_store.py`
- `src/colab_runtime_controller.py`

### Diagnostic and proof files
The `live_*_demo.py` files are intentionally kept in `src/` as lightweight verification utilities used during adapter validation. They are not the production deployment entrypoint, but they help you understand how individual adapters and persistence components were tested in isolation.

### Test path
- `tests/*`
- `src/simulator.py`
- `data/scenario_*.json`

---

## 11. Local setup

### 11.1 Create environment

Use Python 3.11.

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

### 11.2 Run tests

```bash
pytest -q
```

### 11.3 Compile deployment entrypoint

```bash
python -m py_compile main.py
```

---

## 12. Local validation flow

### 12.1 Core logic tests
The local test suite validates:
- preventive request checks
- idle runtime mitigation logic
- budget handling
- approval exceptions
- expired approvals
- unmanaged projects
- disallowed regions
- onboarding and offboarding
- repeated critical incident escalation

### 12.2 Scenario simulator
Run the sample scenario:

```bash
python -m src.simulator data/scenario_student_a.json
```

This produces:
- registry sync result
- request decisions
- runtime decisions
- action plans
- dry run execution records

---

## 13. GCP deployment overview

### 13.1 Required services
The deployed MVP uses these native services:
- Cloud Logging
- Pub/Sub
- Cloud Run
- Cloud Scheduler
- Firestore
- Cloud Resource Manager
- Notebook Runtime / Colab Enterprise API

### 13.2 Required service account
Create a dedicated runtime service account for the function.

Example:
- `guardrail-fn-sa@<PROJECT_ID>.iam.gserviceaccount.com`

The runtime service account should have only the roles needed for:
- Firestore read and write
- project discovery
- notebook runtime stop
- service invocation where required

### 13.3 Deployment entrypoint
The deployed serverless entrypoint is:
- `main.py`
- function target: `guardrail_entrypoint`

### 13.4 Example deploy command

```bash
gcloud run deploy guardrail-orchestrator   --source .   --function guardrail_entrypoint   --base-image python311   --region <REGION>   --service-account guardrail-fn-sa@<PROJECT_ID>.iam.gserviceaccount.com
```

---

## 14. Configuration

The repository should be configured with environment specific values during deployment, not hardcoded in public source where possible.

### Recommended deployment configuration
- organization ID
- project ID
- Firestore profile file path
- runtime stop mode
- region

### Safe defaults
- dry run stop mode is enabled by default
- real destructive mitigation requires explicit opt in

### Real stop flag
Real runtime stop is disabled by default.

To enable actual stop requests:

```bash
GUARDRAIL_REAL_STOP=true
```

Do not enable this unless:
- the runtime resource name is correct
- IAM is correct
- the target environment is safe for real mitigation

---

## 15. Event types handled

### `log_event`
Used for audit log driven processing.

Examples:
- runtime related admin changes
- scheduler job administration
- project or service level admin events

### `scheduled_sweep`
Used for periodic reconciliation.

Examples:
- idle runtime detection
- repeated critical incident handling
- registry reconciliation
- drift detection

---

## 16. Manual live verification steps

### 16.1 Manual Pub/Sub path
Publish a test sweep message:

```bash
gcloud pubsub topics publish guardrail-events --message='{"type":"scheduled_sweep","source":"manual-test"}'
```

Then inspect logs:

```bash
gcloud run services logs read guardrail-orchestrator --region=<REGION> --limit=100
```

Expected:
- event received
- payload parsed
- orchestrator ran successfully

### 16.2 Audit log path
Perform a small admin action such as creating a temporary Pub/Sub topic.

This produces:
- Admin Activity audit log
- Logging sink export
- Pub/Sub event
- serverless function invocation

Expected:
- event classified as `log_event`
- orchestrator executed successfully

### 16.3 Scheduler path
Create a scheduler job that publishes to the shared topic.

Run it manually:

```bash
gcloud scheduler jobs run guardrail-sweep-job --location=<REGION>
```

Expected:
- `scheduled_sweep` payload reaches the function
- orchestrator runs successfully

### 16.4 Runtime stop dry run test
Publish the supplied runtime test payload:

```bash
gcloud pubsub topics publish guardrail-events --message="$(cat data/runtime_stop_test.json)"
```

Expected live result:
- runtime snapshot parsed
- policy engine identifies a critical runtime
- mitigation plan created
- `DRY_RUN_STOP ...` appears in logs
- no destructive stop occurs by default

---

## 17. Proven live in GCP

The following have been verified in the native GCP environment:

- manual Pub/Sub trigger path
- Cloud Logging sink to Pub/Sub path
- Cloud Scheduler to Pub/Sub path
- Cloud Run function invocation
- Firestore persistence
- live GCP project discovery
- event type classification for `log_event` and `scheduled_sweep`
- dry run notebook runtime mitigation path

### Important note
The repository proves real adapter invocation for runtime mitigation, but defaults to dry run mode. This is intentional so you can test safely without accidentally stopping real runtimes.

---

## 18. Security and safe publishing guidance

### Safe to publish
- source code
- tests
- sample JSON
- architecture diagram
- solution document
- deploy instructions
- dry run test commands

### Do not commit
- ADC credentials
- local `.gcloud*` directories
- service account key files
- `.env` with real secrets
- personal billing data
- local cache or virtual environment
- raw credential JSON files

### Recommended `.gitignore`

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
env/
.env
.gcloud-clean/
application_default_credentials.json
*.pem
*.log
```

---

## 19. Requirement coverage summary

This solution addresses the major explicit and implicit requirements:

- automated detection and mitigation
- protection against unplanned high cost runtime usage
- automatic onboarding and offboarding
- support for 1:1 and 1:many principal models
- applicability across PhD Research, Teaching and Learning, Research, and Professional Staff
- scalable shared control plane design
- low cost operational model
- upgradeability through modular architecture
- live GCP native implementation path
- safe reviewer reproducibility through dry run defaults

---

## 20. Known assumptions

- governance metadata is currently represented using profile data rather than a full production metadata registry
- real runtime stop is feature gated for safety
- live notification delivery is intentionally lightweight in the MVP
- notebook runtime stop assumes correct full runtime resource name when real stop is enabled
- platform plumbing details are intentionally simplified in the high level architecture for clarity

---

## 21. Recommended reviewer flow

If you are reviewing this repository, use this order:

### Step 1
Run local tests:

```bash
pytest -q
```

### Step 2
Review the architecture diagram and solution document in `docs/`

### Step 3
Inspect production path files:
- `main.py`
- `src/orchestrator.py`
- `src/engine.py`
- `src/policy.py`
- `src/gcp_project_discovery.py`
- `src/firestore_state_store.py`
- `src/colab_runtime_controller.py`

### Step 4
Run the local scenario simulator

### Step 5
Deploy the serverless entrypoint to GCP

### Step 6
Verify:
- manual Pub/Sub event
- scheduler event
- audit log event
- dry run runtime stop test

---

## 22. Future enhancements

Possible next enhancements include:
- real notification adapter
- richer runtime inventory adapter
- automated project profile store instead of local profile file
- billing export analytics to BigQuery
- more granular approval workflows
- production rollout of real stop after staged validation

---

## 23. Final note

This repository intentionally prioritizes:

- clarity
- modularity
- reproducibility
- safe defaults
- real GCP native execution

over unnecessary service sprawl.

The result is a clean, scalable, reviewer friendly implementation that can be tested locally, deployed natively on GCP, and extended safely into a fuller production control plane.
