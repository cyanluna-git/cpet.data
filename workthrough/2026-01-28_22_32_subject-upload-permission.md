# Subject 테스트 업로드 권한 수정

## 개요
일반 사용자(subject)가 자신의 테스트 데이터를 업로드할 수 있도록 백엔드 권한을 수정했습니다. 기존에는 연구자/관리자만 업로드할 수 있었습니다.

## 주요 변경사항
- `backend/app/api/tests.py`의 `/upload-auto` 엔드포인트 수정
  - `ResearcherUser` → `CurrentUser` 의존성으로 변경
  - Subject 역할 사용자는 자신의 subject_id에만 업로드 가능
  - 연구자/관리자는 기존대로 모든 피험자에게 업로드 가능

### 핵심 코드
```python
# Subject 사용자 권한 검사
if current_user.role in ("user", "subject"):
    if current_user.subject_id is None:
        raise HTTPException(status_code=403, detail="No subject profile linked")
    # 자신의 subject_id로 강제 지정
    subject = await db.execute(select(Subject).where(Subject.id == current_user.subject_id))
    subject_created = False
else:
    # 연구자/관리자: 자동 매칭/생성
    subject, subject_created = await service.find_or_create_subject(parsed_data.subject)
```

## 결과
- Python 문법 검증 완료
- 프론트엔드 빌드 성공
- 131개 단위 테스트 통과

## 다음 단계
- E2E 테스트에서 subject 업로드 시나리오 추가
- 업로드 성공 후 피드백 메시지 개선
