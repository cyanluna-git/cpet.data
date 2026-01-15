---
title: Batch Cloud Run API Requests
impact: MEDIUM-HIGH
impactDescription: Reduces HTTP overhead and request latency by 40-60%
tags: cloud-run, api, batching, performance
---

## Batch Cloud Run API Requests

Group multiple API calls to your Cloud Run backend into a single request where possible. Each HTTP request has overhead.

**Incorrect (multiple API calls):**

```typescript
const loadCohortMetrics = async (cohortId: string) => {
  const basicStats = await fetch(
    `${CLOUD_RUN_URL}/api/cohorts/${cohortId}/stats`
  ).then(r => r.json())

  const respiratoryData = await fetch(
    `${CLOUD_RUN_URL}/api/cohorts/${cohortId}/respiratory`
  ).then(r => r.json())

  const metabolismData = await fetch(
    `${CLOUD_RUN_URL}/api/cohorts/${cohortId}/metabolism`
  ).then(r => r.json())

  return { basicStats, respiratoryData, metabolismData }
}
```

**Correct (batched request):**

```typescript
const loadCohortMetrics = async (cohortId: string) => {
  const response = await fetch(
    `${CLOUD_RUN_URL}/api/cohorts/${cohortId}/metrics`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fields: ['stats', 'respiratory', 'metabolism']
      })
    }
  )
  return response.json()
}
```

Backend FastAPI endpoint:

```python
@app.post("/api/cohorts/{cohort_id}/metrics")
async def get_cohort_metrics(cohort_id: str, body: dict):
    results = {}
    if 'stats' in body.get('fields', []):
        results['basicStats'] = await get_stats(cohort_id)
    if 'respiratory' in body.get('fields', []):
        results['respiratoryData'] = await get_respiratory(cohort_id)
    if 'metabolism' in body.get('fields', []):
        results['metabolismData'] = await get_metabolism(cohort_id)
    return results
```

This reduces round-trips from 3 to 1, significantly improving perceived performance.

Reference: [HTTP Request Optimization](https://cloud.google.com/run/docs/quickstarts)
