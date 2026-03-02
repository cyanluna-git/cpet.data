# CPET 테스트 자동 업로드 기능 구현

## Overview
AdminDataPage에서 COSMED Excel 파일을 업로드하면 피험자를 자동으로 매칭하거나 새로 생성하는 기능을 구현했습니다. 연구자/어드민이 피험자를 먼저 등록하지 않아도 테스트 데이터를 바로 업로드할 수 있습니다.

## Context
- **요구사항**: Frontend에서 바로 시험 데이터 업로드
- **대상 사용자**: 연구자(Researcher), 어드민(Admin)
- **핵심 기능**: 피험자 자동 매칭/생성 후 테스트 파싱

## Changes Made

### 1. Backend: TestUploadAutoResponse 스키마 추가
- **파일**: `backend/app/schemas/test.py`
- 새로운 응답 스키마 추가
- `subject_created` 필드로 피험자 생성 여부 표시

### 2. Backend: find_or_create_subject 서비스 메서드 추가
- **파일**: `backend/app/services/test.py`
- 피험자 자동 매칭 로직 구현
- 매칭 우선순위:
  1. `research_id` 정확히 일치
  2. `last_name_first_name` 형식으로 검색
  3. `encrypted_name` 일치
- 매칭 실패 시 새 피험자 자동 생성

### 3. Backend: upload_test_auto 엔드포인트 추가
- **파일**: `backend/app/api/tests.py`
- `POST /api/tests/upload-auto` 엔드포인트
- `ResearcherUser` 권한 필요
- 파일 검증 (xlsx/xls, 50MB 제한)

### 4. Frontend: uploadTestAuto API 함수 추가
- **파일**: `frontend/src/lib/api.ts`
- `TestUploadAutoResponse` 타입 정의
- `uploadTestAuto()` 함수 구현

### 5. Frontend: TestUploadModal 컴포넌트 생성
- **파일**: `frontend/src/components/TestUploadModal.tsx` (새 파일)
- 드래그 & 드롭 파일 업로드 UI
- 고급 설정 (계산 방법, 평활화 윈도우)
- 업로드 결과 표시 (피험자 생성 여부 포함)

### 6. Frontend: AdminDataPage에 업로드 버튼 추가
- **파일**: `frontend/src/components/pages/AdminDataPage.tsx`
- "테스트 업로드" 버튼 추가
- 업로드 성공 시 테이블/통계 자동 새로고침

### 7. DB 스키마 수정
- **파일**: `backend/app/models/cpet_test.py`
- `parsing_status` 컬럼: `VARCHAR(20)` → `VARCHAR(50)`
- 이유: `'skipped_protocol_mismatch'`가 20자 초과

## Code Examples

### Backend: 피험자 자동 매칭 로직
```python
# backend/app/services/test.py
async def find_or_create_subject(
    self,
    subject_info: SubjectInfo,
) -> Tuple[Subject, bool]:
    """
    매칭 우선순위:
    1. research_id 정확히 일치
    2. last_name + first_name으로 생성한 research_id 일치
    3. encrypted_name 일치
    """
    first_name = (subject_info.first_name or "").strip()
    last_name = (subject_info.last_name or "").strip()
    research_id = (subject_info.research_id or "").strip()
    
    # 이름 기반 research_id 생성
    name_based_id = f"{last_name}_{first_name}" if last_name and first_name else ""
    
    # 1. research_id로 검색
    if research_id:
        result = await self.db.execute(
            select(Subject).where(
                func.lower(Subject.research_id) == research_id.lower()
            )
        )
        subject = result.scalar_one_or_none()
        if subject:
            return subject, False
    
    # ... 추가 매칭 로직 ...
    
    # 매칭 실패 → 새 피험자 생성
    new_subject = Subject(
        research_id=final_research_id,
        encrypted_name=full_name or None,
        # ... 기타 필드
    )
    self.db.add(new_subject)
    return new_subject, True
```

### Backend: upload-auto 엔드포인트
```python
# backend/app/api/tests.py
@router.post("/upload-auto", response_model=TestUploadAutoResponse, status_code=status.HTTP_201_CREATED)
async def upload_test_auto(
    db: DBSession,
    current_user: ResearcherUser,
    file: UploadFile = File(...),
    calc_method: str = Form("Frayn"),
    smoothing_window: int = Form(10),
):
    # 1. 파일에서 피험자 정보 추출
    parser = COSMEDParser()
    parsed_data = parser.parse_file(tmp_path)
    
    # 2. 피험자 자동 매칭/생성
    subject, subject_created = await service.find_or_create_subject(parsed_data.subject)
    
    # 3. 테스트 업로드
    test, errors, warnings = await service.upload_and_parse(...)
    
    return TestUploadAutoResponse(
        test_id=test.test_id,
        subject_created=subject_created,
        subject_name=subject.encrypted_name or subject.research_id,
        # ...
    )
```

### Frontend: 업로드 모달 컴포넌트
```tsx
// frontend/src/components/TestUploadModal.tsx
export function TestUploadModal({ open, onClose, onSuccess }: TestUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  
  const handleUpload = async () => {
    const response = await api.uploadTestAuto(file, {
      calc_method: calcMethod,
      smoothing_window: smoothingWindow,
    });
    
    if (response.subject_created) {
      toast.success(`새 피험자 "${response.subject_name}"가 생성되었습니다.`);
    } else {
      toast.success(`기존 피험자 "${response.subject_name}"에 테스트가 추가되었습니다.`);
    }
    
    onSuccess(); // 테이블 새로고침
  };
  
  return (
    <Dialog open={open} onOpenChange={onClose}>
      {/* 드래그 & 드롭 영역 */}
      {/* 고급 설정 (Collapsible) */}
      {/* 업로드 결과 표시 */}
    </Dialog>
  );
}
```

## Verification Results

### Frontend Build
```bash
> npm run build

vite v6.4.1 building for production...
✓ 2407 modules transformed.
dist/index.html                   0.46 kB │ gzip:   0.29 kB
dist/assets/index-_L7ojCM2.js 1,040.60 kB │ gzip: 298.36 kB
✓ built in 2.40s
```

### Backend Syntax Check
```bash
> python3 -m py_compile app/api/tests.py app/services/test.py app/schemas/test.py
Syntax check passed!
```

### DB Migration
```bash
> docker exec cpet-db psql -U cpet_user -d cpet_db -c \
  "ALTER TABLE cpet_tests ALTER COLUMN parsing_status TYPE VARCHAR(50);"
ALTER TABLE
```

## Git Commits

1. `feat: add auto-upload test with subject auto-matching` (3193d5a)
   - 6 files changed, 1376 insertions(+)

2. `fix: increase parsing_status column length to VARCHAR(50)` (feb8f23)
   - 2 files changed, 17 insertions(+)

## API Reference

### POST /api/tests/upload-auto

**Request:**
```
Content-Type: multipart/form-data
Authorization: Bearer {token}

file: <binary> (required)
calc_method: "Frayn" | "Jeukendrup" (optional, default: "Frayn")
smoothing_window: number (optional, default: 10)
```

**Response (201):**
```json
{
  "test_id": "uuid",
  "subject_id": "uuid",
  "subject_created": true,
  "subject_name": "Park Yongdoo",
  "source_filename": "test.xlsx",
  "parsing_status": "success",
  "parsing_errors": null,
  "parsing_warnings": null,
  "data_points_count": 1250,
  "created_at": "2026-01-24T10:30:00Z"
}
```

## Next Steps
- 다중 파일 업로드 지원 고려
- 업로드 진행률 표시 개선
- 중복 테스트 감지 로직 추가
