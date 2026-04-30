# CPET Pipeline Skill

## Metadata

```yaml
name: cpet-pipeline
version: 1.0.0
description: Process CPET submission data and generate analysis report
author: CPET Team
triggers:
  - channel:
      source: cpet-webhook
      type: new_submission
```

## Overview

This skill activates when Claude Code receives a channel event from the CPET
platform webhook. It orchestrates the full pipeline: parse submission data,
run analysis, generate a report, publish it, and update the job status.

Event payload shape:

```json
{
  "submission_id": "uuid",
  "job_id": "uuid",
  "workspace_path": "data/workspaces/<uuid>",
  "description": "Natural language test description from the user",
  "files": [
    {"name": "test.xlsx", "extension": "xlsx", "size_bytes": 123456}
  ]
}
```

---

## Workflow

When you receive a `<channel source="cpet-webhook" type="new_submission">` event,
execute the following 7 steps in order. If any step fails, jump to the error
handling section at the bottom.

### Step 1: Parse Channel Event

Parse the JSON content from the channel event body. Extract:

- `submission_id` (string, UUID)
- `job_id` (string, UUID)
- `workspace_path` (string, relative path to workspace directory)
- `description` (string, natural language test description)
- `files` (array, list of uploaded file metadata)

Validate that all required fields are present. If any are missing, update the
job as failed immediately (skip to Step 7 with error).

### Step 2: Update Job Status to Processing

Mark the job as actively being worked on so the dashboard shows progress.

```bash
python3 -c "
from pathlib import Path
from server.db import update_job_status
update_job_status(Path('data/cpet_platform.db'), '$JOB_ID', 'processing')
"
```

Replace `$JOB_ID` with the actual job_id from Step 1.

### Step 3: Understand the Test (AI Judgment)

Read the `description` field to determine:

1. **Protocol type**: lactate threshold / VO2max / submaximal / other
2. **Special notes**: FTP value, estimated thresholds, test conditions, rider weight
3. **Missing data**: Cross-reference the `files` list against what is expected
   for this protocol type:
   - Lactate threshold test: expects COSMED XLSX + Lactate (CSV/MD) + optional FIT/ZWO
   - VO2max test: expects COSMED XLSX + optional FIT/ZWO
   - Submaximal test: expects COSMED XLSX only

Flag any warnings (e.g., "Lactate test submitted but no lactate data file found")
but do NOT fail the job for missing optional files. Only the COSMED XLSX is
strictly required.

### Step 3.5: Verify Workspace (Restore if Missing)

Before running the pipeline, confirm that `$WORKSPACE_PATH/raw/` exists and contains files.
If the directory is missing or empty, restore the raw files from the DB:

```bash
python3 -c "
from pathlib import Path
from server.db import restore_submission_files
from server.workspace import create_workspace

submission_id = '$SUBMISSION_ID'
db_path = Path('data/cpet_platform.db')
workspace = Path('$WORKSPACE_PATH')
raw_dir = workspace / 'raw'

files_exist = raw_dir.is_dir() and any(raw_dir.iterdir())
if not files_exist:
    stored = restore_submission_files(db_path, submission_id)
    if not stored:
        raise RuntimeError(f'no source files in DB for submission {submission_id}')
    data_dir = Path('data')
    create_workspace(data_dir, submission_id, stored)
    print(f'Restored {len(stored)} file(s) into {raw_dir}')
else:
    print(f'Workspace raw/ OK: {list(raw_dir.iterdir())}')
"
```

Replace `$SUBMISSION_ID` and `$WORKSPACE_PATH` with values from Step 1.
If the restore raises RuntimeError, jump to Step 7 with that error message.

### Step 4: Run Pipeline

Execute the analysis pipeline on the workspace:

```bash
python3 -m pipeline --workspace $WORKSPACE_PATH --verbose
```

Replace `$WORKSPACE_PATH` with the actual workspace_path from Step 1.

**Exit code handling:**
- `0` = success, proceed to Step 5
- `1` = validation error (missing required files, data out of range)
- `2` = analysis error (algorithm failure)

If exit code is non-zero, capture stderr and jump to Step 7 with error.

### Step 5: Quality Review (AI Judgment)

Read the generated report at `$WORKSPACE_PATH/report/index.html` briefly. Check:

1. **FatMax value** is physiologically reasonable: 0.2 ~ 1.2 g/min fat oxidation
2. **VO2max** is within expected range for the subject (typically 30 ~ 80 ml/kg/min)
3. **Charts have data points** (not empty SVG/canvas elements)
4. **Lactate thresholds** (if lactate data present): LT1 < LT2 < VO2max power
5. **Heart rate data** is present and reasonable (resting ~60, max ~180-210)

If any check fails, log a warning but do NOT fail the job. Include the warning
in the completion notes. These are sanity checks, not hard gates.

### Step 6: Publish Report

Use the publish module to copy the report to the public directory:

```bash
python3 -c "
from pathlib import Path
from server.publish import publish_report
slug = publish_report(
    workspace=Path('$WORKSPACE_PATH'),
    subject_name='$SUBJECT_NAME',
    test_date='$TEST_DATE',
)
print(f'Published to: {slug}')
"
```

Replace:
- `$WORKSPACE_PATH` with workspace_path from Step 1
- `$SUBJECT_NAME` with the subject name from the submission record
- `$TEST_DATE` with the test date from the submission record

To get the subject name and test date:

```bash
python3 -c "
from pathlib import Path
from server.db import get_submission
sub = get_submission(Path('data/cpet_platform.db'), '$SUBMISSION_ID')
print(f\"subject_name={sub['subject_name']}\")
print(f\"test_date={sub['test_date']}\")
"
```

### Step 7: Update Job Status

**On success:**

```bash
python3 -c "
from pathlib import Path
from server.db import update_job_status
update_job_status(
    Path('data/cpet_platform.db'),
    '$JOB_ID',
    'done',
    report_slug='$SLUG',
    report_url='https://cpet.cyanluna.com/report/$SLUG/',
)
"
```

**On failure** (any step failed):

```bash
python3 -c "
from pathlib import Path
from server.db import update_job_status
update_job_status(
    Path('data/cpet_platform.db'),
    '$JOB_ID',
    'failed',
    error_message='''$ERROR_MESSAGE''',
)
"
```

Truncate error_message to 500 characters maximum.

---

## Error Handling

If any step fails:

1. Capture the error message (stderr output, exception text, or descriptive note)
2. Truncate to 500 characters
3. Execute Step 7 failure path
4. Stop processing (do not continue to subsequent steps)

Common failure modes:

| Failure | Step | Recovery |
|---------|------|----------|
| Missing required fields in event | 1 | Fail job with "Invalid channel event: missing {field}" |
| Pipeline validation error | 4 | Fail job with pipeline stderr |
| Pipeline analysis error | 4 | Fail job with pipeline stderr |
| Report file not generated | 6 | Fail job with "Report not found at {path}" |
| Publish directory permission error | 6 | Fail job with "Publish failed: {error}" |

## Notes

- All database operations use `Path('data/cpet_platform.db')` as the db_path
- The pipeline operates on per-workspace SQLite databases (`analysis.db`),
  separate from the platform database
- Published reports are served by Nginx at `cpet.cyanluna.com/report/<slug>/`
- The workspace directory structure is:
  ```
  data/workspaces/<uuid>/
    raw/          # uploaded files
    analysis.db   # created by pipeline
    report/
      index.html  # created by pipeline
  ```
