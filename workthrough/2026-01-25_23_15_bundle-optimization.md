# 번들 사이즈 최적화

## 개요
Vercel React Best Practices 가이드라인을 적용하여 프론트엔드 번들 사이즈를 69% 감소시켰습니다.

## 주요 변경사항
- 적용한 것: `bundle-dynamic-imports` - React.lazy()로 페이지 컴포넌트 lazy loading
- 적용한 것: `bundle-barrel-imports` - recharts 전체 import 대신 선택적 import
- 적용한 것: `async-suspense-boundaries` - Suspense로 로딩 상태 처리

## 결과

### Before
```
dist/assets/index-*.js    1,055.67 kB │ gzip: 300.75 kB
```

### After
```
dist/assets/index-*.js      324.46 kB │ gzip: 105.28 kB  (-69%)
```

## 핵심 코드

### React.lazy() 적용 (App.tsx)
```tsx
// Before: 정적 import
import { MetabolismPage } from '@/components/pages/MetabolismPage';

// After: 동적 import
const MetabolismPage = lazy(() =>
  import('@/components/pages/MetabolismPage')
    .then(m => ({ default: m.MetabolismPage }))
);
```

### Recharts 선택적 import (chart.tsx)
```tsx
// Before: 전체 라이브러리
import * as RechartsPrimitive from "recharts";

// After: 필요한 컴포넌트만
import { ResponsiveContainer, Tooltip, Legend } from "recharts";
```

## 번들 분리 결과
- 11개 페이지가 개별 청크로 분리
- 차트 라이브러리(376kB)는 차트 페이지 접근 시에만 로드
- 로그인/대시보드 페이지 초기 로드 속도 대폭 개선
