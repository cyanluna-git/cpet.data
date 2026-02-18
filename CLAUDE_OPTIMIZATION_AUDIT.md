# Claude Code Memory Optimization Audit

## 📊 현재 상태 분석

### ✅ 좋은 점

| 항목 | 상태 | 설명 |
|------|------|------|
| **Root CLAUDE.md** | ✅ 최적 | 85줄 (200줄 제한 이내) |
| **Modular Rules** | ✅ 구현됨 | `.claude/rules/` 5개 파일로 모듈화 |
| **Sub-project Guides** | ✅ 있음 | backend/.claude, frontend/.claude 분리 |
| **규칙 범위** | ✅ 명확 | 언어별(Python/TypeScript) 구분 |
| **Import 시스템** | ✅ 사용 중 | `@../../.claude/rules/` 상대 경로 import |

### ⚠️ 개선 가능 영역

#### 1. **Rules에 Paths Frontmatter 부재**
```markdown
현재: rules 파일들이 조건부 적용 없음
권장: 경로별 조건부 적용으로 효율성 ↑
```

**예시:**
```yaml
# code-style.md에 추가
---
paths:
  - "backend/**/*.py"     # Python 파일에만 적용
  - "frontend/src/**/*.ts" # TypeScript 파일에만 적용
---
```

#### 2. **Backend/Frontend Rules 분리 부족**
```
현재: 모든 규칙을 하나의 rules 폴더에서 공유
개선: backend/frontend별 특화 rules 추가 가능
```

#### 3. **Auto Memory 미설정**
```
현재: Auto memory 설정/구조 없음
개선: ~/.claude/projects/<project>/memory/MEMORY.md 활용
```

#### 4. **각 Rules 파일의 명확성**
- 일부 파일에 범위가 모호함 (예: security.md)
- 경로 지정으로 자동 적용 범위 명확화 필요

---

## 🎯 최적화 실행 계획

### Phase 1: Rules 파일 개선 (우선순위: 높음)

#### 1-1. code-style.md에 Paths Frontmatter 추가
```yaml
---
paths:
  - "backend/**/*.py"
  - "frontend/src/**/*.{ts,tsx}"
---
```

#### 1-2. api-conventions.md에 경로 지정
```yaml
---
paths:
  - "backend/app/api/**/*.py"
  - "frontend/src/lib/**/*.ts"
---
```

#### 1-3. testing.md에 경로 지정
```yaml
---
paths:
  - "backend/tests/**/*.py"
  - "frontend/src/**/*.test.{ts,tsx}"
---
```

#### 1-4. security.md에 경로 지정
```yaml
---
paths:
  - "backend/app/**/*.py"
  - "frontend/src/**/*.{ts,tsx}"
---
```

#### 1-5. commit-workflow.md
```yaml
---
paths: [] # 모든 파일에 적용 (Git 관련)
---
```

### Phase 2: 언어별 Rules 구조화 (선택사항)

```
.claude/rules/
├── general/
│   └── commit-workflow.md
├── backend/
│   ├── python-style.md
│   ├── fastapi-conventions.md
│   └── testing.md
└── frontend/
    ├── react-style.md
    ├── typescript-conventions.md
    └── testing.md
```

**장점:**
- 명확한 범위 구분
- 유지보수 용이
- 팀원이 찾기 쉬움

### Phase 3: Auto Memory 설정 (선택사항)

```
~/.claude/projects/cpet.db/memory/
├── MEMORY.md           # 인덱스 (자동 200줄 로드)
├── patterns.md         # 프로젝트 패턴
├── debugging.md        # 버그 해결 기록
└── architecture.md     # 아키텍처 이해
```

**사용법:**
```bash
# 설정 (강제 활성화)
export CLAUDE_CODE_DISABLE_AUTO_MEMORY=0

# 메모리 관리
/memory  # 메모리 파일 열기
```

---

## 📋 실행 체크리스트

### 필수 (Recommended)
- [ ] code-style.md에 paths frontmatter 추가
- [ ] api-conventions.md에 paths 추가
- [ ] testing.md에 paths 추가
- [ ] security.md에 paths 추가
- [ ] commit-workflow.md paths 정리

### 선택 (Optional)
- [ ] Rules 구조를 backend/frontend로 세분화
- [ ] Auto memory 구조 설정 및 활용 시작

---

## 💡 최적화 효과

| 개선사항 | 효과 | 영향도 |
|---------|------|--------|
| **Paths Frontmatter** | Claude가 불필요한 규칙 무시 → 콘텍스트 절약 | 높음 |
| **명확한 구조** | 팀원들이 규칙 이해도 ↑ | 중간 |
| **Auto Memory** | 세션 간 학습 누적 | 낮음-중간 |

---

## 📖 참고

- Claude Code Memory Docs: https://code.claude.com/docs/en/memory
- Paths Frontmatter 문법: YAML `paths` array with glob patterns
- 최대 깊이: imports 최대 5 hops

