---
title: Virtual Scroll for CPET Data Tables
impact: MEDIUM
impactDescription: Enables rendering of 10,000+ rows smoothly, 60fps scrolling
tags: cpet, rendering, performance, virtualization
---

## Virtual Scroll for CPET Data Tables

When displaying large CPET datasets or subject lists, render only visible rows to keep the DOM lean and scrolling smooth.

**Incorrect (renders all rows):**

```typescript
const SubjectTable = ({ subjects }) => {
  return (
    <table>
      <tbody>
        {subjects.map(subject => (
          <tr key={subject.id}>
            <td>{subject.name}</td>
            <td>{subject.age}</td>
            <td>{subject.test_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ❌ If subjects has 10,000 rows, all 10,000 <tr> elements are in the DOM
```

**Correct (virtualized):**

```typescript
import { FixedSizeList } from 'react-window'

const SubjectTable = ({ subjects }) => {
  const Row = ({ index, style }) => (
    <div style={style}>
      <span>{subjects[index].name}</span>
      <span>{subjects[index].age}</span>
      <span>{subjects[index].test_count}</span>
    </div>
  )

  return (
    <FixedSizeList
      height={600}
      itemCount={subjects.length}
      itemSize={35}
      width="100%"
    >
      {Row}
    </FixedSizeList>
  )
}

// ✅ Only ~20 visible rows rendered, DOM stays lean
```

**Alternative: Use a modern table library with built-in virtualization:**

```typescript
import { useReactTable, getCoreRowModel } from '@tanstack/react-table'
import { VirtualScroller } from '@tanstack/react-table/row-virtual'

const virtualizer = useVirtualizer({
  count: subjects.length,
  getScrollElement: () => tableContainerRef.current,
  estimateSize: () => 35,
})
```

Virtualization keeps scrolling smooth even with thousands of rows.

Reference: [React Window](https://react-window.vercel.app), [TanStack Table Virtualization](https://tanstack.com/table/v8/docs/guide/virtualization)
