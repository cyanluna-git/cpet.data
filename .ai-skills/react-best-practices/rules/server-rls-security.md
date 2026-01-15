---
title: Optimize Supabase Row-Level Security
impact: HIGH
impactDescription: Prevents unauthorized data access, reduces database computation
tags: supabase, security, performance, rls
---

## Optimize Supabase Row-Level Security

Always use Row-Level Security (RLS) policies with indexed columns. Never rely only on client-side filtering.

**Incorrect (client-side filtering only):**

```typescript
// This fetches ALL data, then filters on client - exposes data!
const { data: allTests } = await supabase
  .from('cpet_tests')
  .select('*')

// Dangerous - data is already fetched, user could see it
const userTests = allTests.filter(t => t.user_id === userId)
```

**Correct (RLS policy enforced):**

```typescript
// Backend: Create RLS policy in Supabase
-- Only users can see their own CPET tests
CREATE POLICY "Users see own tests"
  ON cpet_tests
  USING (auth.uid() = user_id)

-- Frontend: Query is automatically filtered at database level
const { data: userTests, error } = await supabase
  .from('cpet_tests')
  .select('*')
  // Only rows where user_id = auth.uid() are returned

// Ensure user_id is indexed for fast filtering
CREATE INDEX idx_cpet_tests_user_id ON cpet_tests(user_id)
```

**Optimized query with indexed join:**

```typescript
const { data: cohortTests } = await supabase
  .from('cpet_tests')
  .select(`
    *,
    subjects (id, name),
    cohorts (id, name)
  `)
  .eq('cohorts.id', cohortId)  // RLS filters by cohort permission
  .order('test_date', { ascending: false })
  .limit(100)
```

**Benefits:**
- Data security at database level
- Filters applied before data leaves database
- Faster queries on indexed columns
- Can't be bypassed by client-side code

Reference: [Supabase Row-Level Security](https://supabase.com/docs/guides/auth/row-level-security)
