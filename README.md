# Pipeline Scheduler Commands

This document explains how to initialize the environment, activate the Python virtual environment, schedule repositories, and check scheduler status.

## 1. Activate the Environment

First, source the required environment and worker configuration scripts:

```bash
source _hf_cache_env.sh
source _pipeline_workers_single.sh
```

Then activate the project's Python virtual environment:

```bash
source .venv/bin/activate
```

> On Windows, use:
>
> ```powershell
> .venv\Scripts\Activate.ps1
> ```

---

## 2. Schedule Repositories

Once the virtual environment is activated, run the pipeline using the `pipeline` command:

```bash
pipeline schedule \
  --repos <REPOSITORY_LIST_FILE> \
  --scheduler-file <SCHEDULER_FILE> \
  2>&1 | tee -a <LOG_FILE>
```

### Example

```bash
pipeline schedule \
  --repos quality_repo.txt \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/quality_repo.json" \
  2>&1 | tee -a logs/quality_repo.log
```

### Parameters

| Parameter | Description |
|---|---|
| `--repos` | Path to the file containing the repositories to process |
| `--scheduler-file` | Path to the scheduler state/configuration file |
| `tee -a` | Appends output to the log file while also displaying it in the terminal |

---

## 3. Check Scheduler Status

To check the status of repositories using only the scheduler:

```bash
pipeline status \
  --scheduler-only \
  --scheduler-file <SCHEDULER_FILE> \
  --repos <REPOSITORY_LIST_FILE>
```

### Example

```bash
pipeline status \
  --scheduler-only \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/repos_retry.json" \
  --repos repository_retry.txt
```

### Parameters

| Parameter | Description |
|---|---|
| `--scheduler-only` | Checks status using scheduler information only |
| `--scheduler-file` | Path to the scheduler state/configuration file |
| `--repos` | Path to the repository list |

---

## 4. Complete Workflow

### Step 1 — Load environment configuration

```bash
source _hf_cache_env.sh
source _pipeline_workers_single.sh
```

### Step 2 — Activate the virtual environment

```bash
source .venv/bin/activate
```

### Step 3 — Schedule repositories

```bash
pipeline schedule \
  --repos quality_repo.txt \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/quality_repo.json" \
  2>&1 | tee -a logs/quality_repo.log
```

### Step 4 — Check retry repository status

```bash
pipeline status \
  --scheduler-only \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/repos_retry.json" \
  --repos repository_retry.txt
```

---

## 5. Avoid Hard-Coded Paths

Do not use machine-specific paths such as:

```bash
/workspace/shyam/hf-cache/scheduler/quality_repo.json
```

Instead, use an environment variable:

```bash
"${HF_CACHE_DIR}/scheduler/quality_repo.json"
```

For example:

```bash
export HF_CACHE_DIR="/path/to/hf-cache"
```

Then the scheduler file can be referenced as:

```bash
"${HF_CACHE_DIR}/scheduler/quality_repo.json"
```

This keeps the commands independent of a specific user's home directory or workspace location.

---

## 6. Using `.venv` Without Activating It

If you don't want to activate the virtual environment, you can invoke the executable directly:

```bash
.venv/bin/pipeline schedule \
  --repos quality_repo.txt \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/quality_repo.json" \
  2>&1 | tee -a logs/quality_repo.log
```

And for status:

```bash
.venv/bin/pipeline status \
  --scheduler-only \
  --scheduler-file "${HF_CACHE_DIR}/scheduler/repos_retry.json" \
  --repos repository_retry.txt
```

Using `.venv/bin/pipeline` explicitly ensures that the command always runs with the project's virtual environment.
