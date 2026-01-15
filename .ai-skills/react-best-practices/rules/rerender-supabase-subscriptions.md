---
title: Cache Supabase Real-Time Subscriptions
impact: MEDIUM-HIGH
impactDescription: Reduces memory usage and prevents duplicate listeners
tags: supabase, real-time, performance, memory
---

## Cache Supabase Real-Time Subscriptions

Don't create duplicate real-time subscriptions. Store subscription references and clean up properly on unmount.

**Incorrect (memory leak with duplicate subscriptions):**

```typescript
const SubjectMonitor = ({ subjectId }) => {
  useEffect(() => {
    const subscription = supabase
      .from(`subjects:id=eq.${subjectId}`)
      .on('*', (payload) => {
        console.log('Change:', payload)
      })
      .subscribe()
    // ❌ Missing cleanup - subscription persists on every re-render
  }, [subjectId])

  return <div>Subject Monitor</div>
}
```

**Correct (cached with cleanup):**

```typescript
const SubjectMonitor = ({ subjectId }) => {
  const subscriptionRef = useRef<RealtimeChannel | null>(null)

  useEffect(() => {
    // Clean up previous subscription
    if (subscriptionRef.current) {
      supabase.removeChannel(subscriptionRef.current)
    }

    // Create new subscription
    subscriptionRef.current = supabase
      .channel(`subjects:${subjectId}`)
      .on('postgres_changes', 
        { event: '*', schema: 'public', table: 'subjects', filter: `id=eq.${subjectId}` },
        (payload) => {
          console.log('Change:', payload)
        }
      )
      .subscribe()

    // Cleanup on unmount or dependency change
    return () => {
      if (subscriptionRef.current) {
        supabase.removeChannel(subscriptionRef.current)
      }
    }
  }, [subjectId])

  return <div>Subject Monitor</div>
}
```

**Gotcha: Realtime connections are persistent.** Failing to clean up subscriptions can cause memory leaks and duplicate event handlers.

Reference: [Supabase Realtime Documentation](https://supabase.com/docs/guides/realtime)
