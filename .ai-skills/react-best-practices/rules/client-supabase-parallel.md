---
title: Parallelize Supabase Queries
impact: CRITICAL
impactDescription: Eliminates sequential database round-trips, reduces query time by 50-80%
tags: supabase, database, parallelization, async
---

## Parallelize Supabase Queries

Don't fetch related data sequentially. Use `Promise.all()` to execute independent Supabase queries in parallel.

**Incorrect (waterfalls):**

```typescript
// Fetches subjects first, then loads data for each subject sequentially
const getSubjectAnalysis = async (cohortId: string) => {
  const { data: subjects } = await supabase
    .from('subjects')
    .select('*')
    .eq('cohort_id', cohortId)

  const results = []
  for (const subject of subjects) {
    const { data: cpetTests } = await supabase
      .from('cpet_tests')
      .select('*')
      .eq('subject_id', subject.id)
    results.push({ subject, cpetTests })
  }
  return results
}
```

**Correct (parallel):**

```typescript
// Fetches all data in parallel
const getSubjectAnalysis = async (cohortId: string) => {
  const { data: subjects } = await supabase
    .from('subjects')
    .select('*')
    .eq('cohort_id', cohortId)

  const results = await Promise.all(
    subjects.map(async (subject) => {
      const { data: cpetTests } = await supabase
        .from('cpet_tests')
        .select('*')
        .eq('subject_id', subject.id)
      return { subject, cpetTests }
    })
  )
  return results
}
```

This pattern is especially important with Supabase as each `.select()` is an HTTP request. Parallelization dramatically reduces total latency.

Reference: [Supabase Client Library](https://supabase.com/docs/reference/javascript/select)
