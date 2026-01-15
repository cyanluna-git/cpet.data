---
title: Memoize CPET Data Transformations
impact: MEDIUM
impactDescription: Prevents redundant calculations on metabolic data, 30-50% faster renders
tags: cpet, performance, memoization, useMemo
---

## Memoize CPET Data Transformations

CPET data requires expensive calculations (VO2 metrics, VCO2 analysis, workload conversions). Memoize transformations to prevent recalculations.

**Incorrect (recalculates on every render):**

```typescript
const CPETAnalysisChart = ({ testData }) => {
  // This expensive calculation runs on every render
  const processedMetrics = testData.map(point => ({
    time: point.time,
    vo2_rel: point.vo2 / testData.subject.weight,
    vcg_rel: point.vcg / testData.subject.weight,
    workload: calculateWorkload(point.watts),
    anaerobic_threshold: findAT(testData)
  }))

  return (
    <AreaChart data={processedMetrics}>
      <Area dataKey="vo2_rel" />
    </AreaChart>
  )
}
```

**Correct (memoized):**

```typescript
import { useMemo } from 'react'

const CPETAnalysisChart = ({ testData }) => {
  const processedMetrics = useMemo(() => {
    const at = findAT(testData)
    return testData.map(point => ({
      time: point.time,
      vo2_rel: point.vo2 / testData.subject.weight,
      vcg_rel: point.vcg / testData.subject.weight,
      workload: calculateWorkload(point.watts),
      anaerobic_threshold: at
    }))
  }, [testData.id, testData.subject.weight, testData.data]) // Depend only on data content

  return (
    <AreaChart data={processedMetrics}>
      <Area dataKey="vo2_rel" />
    </AreaChart>
  )
}
```

**Important:** For CPET data, include only the data ID and critical values in dependencies, not the entire object reference.

Reference: [React useMemo](https://react.dev/reference/react/useMemo)
