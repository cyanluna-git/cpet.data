---
title: Use Server Components for Data-Heavy Pages
impact: HIGH
impactDescription: Moves computation to server, reduces client bundle by 50-70%, instant first paint
tags: server-side, next-js, performance, data-fetching
---

## Use Server Components for Data-Heavy Pages

CPET analysis pages are data-heavy. Use Next.js Server Components to fetch and process data on the server, send only the UI to the client.

**Incorrect (client-side fetching):**

```typescript
// app/cohorts/[id]/analysis/page.tsx - Client Component
'use client'

import { useEffect, useState } from 'react'

export default function CohortAnalysisPage({ params }) {
  const [cohortData, setCohortData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    fetch(`/api/cohorts/${params.id}/full-analysis`)
      .then(r => r.json())
      .then(data => {
        setCohortData(data)
        setIsLoading(false)
      })
  }, [params.id])

  if (isLoading) return <div>Loading...</div>
  
  return <CohortAnalysisChart data={cohortData} />
}
```

**Correct (server-side with Server Components):**

```typescript
// app/cohorts/[id]/analysis/page.tsx - Server Component
import { getCohortAnalysis } from '@/services/cohort'
import CohortAnalysisChart from '@/components/CohortAnalysisChart'

export default async function CohortAnalysisPage({ params }) {
  // Fetch on the server - no waiting on client
  const cohortData = await getCohortAnalysis(params.id)

  return <CohortAnalysisChart data={cohortData} />
}
```

Backend service:

```typescript
// services/cohort.ts
import { supabase } from '@/lib/supabase-server'

export async function getCohortAnalysis(cohortId: string) {
  const { data } = await supabase
    .from('cohorts')
    .select(`
      *,
      subjects (
        *,
        cpet_tests (*)
      )
    `)
    .eq('id', cohortId)
    .single()

  // Heavy computation happens on server
  return processMetricsOnServer(data)
}
```

**Benefits:**
- No JavaScript sent to browser for data fetching
- Instant page render (no loading state)
- Secure database access (no API keys exposed)
- Better search engine indexing

Reference: [Next.js Server Components](https://nextjs.org/docs/app/building-your-application/rendering/server-components)
