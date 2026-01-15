---
title: Lazy Load Metabolic Charts
impact: MEDIUM
impactDescription: Reduces initial bundle by 200-400KB, improves first contentful paint
tags: bundle, code-splitting, charts, next-dynamic
---

## Lazy Load Metabolic Charts

Heavy charting libraries (Recharts, Chart.js) should be loaded on-demand via Next.js dynamic imports, not bundled upfront.

**Incorrect (blocks initial load):**

```typescript
// app/metabolism/page.tsx
import MetabolismChart from '@/components/MetabolismChart'
import MetabolismPatternChart from '@/components/MetabolismPatternChart'

export default function MetabolismPage() {
  return (
    <div>
      <MetabolismChart testId={params.testId} />
      <MetabolismPatternChart testId={params.testId} />
    </div>
  )
}
```

**Correct (lazy loaded):**

```typescript
// app/metabolism/page.tsx
import dynamic from 'next/dynamic'
import { Suspense } from 'react'

const MetabolismChart = dynamic(
  () => import('@/components/MetabolismChart'),
  { loading: () => <div>Loading chart...</div> }
)

const MetabolismPatternChart = dynamic(
  () => import('@/components/MetabolismPatternChart'),
  { loading: () => <div>Loading pattern...</div> }
)

export default function MetabolismPage() {
  return (
    <div>
      <Suspense fallback={<div>Loading...</div>}>
        <MetabolismChart testId={params.testId} />
        <MetabolismPatternChart testId={params.testId} />
      </Suspense>
    </div>
  )
}
```

Charts load only when needed, keeping your initial bundle small and fast.

Reference: [Next.js Dynamic Imports](https://nextjs.org/docs/advanced-features/dynamic-import)
