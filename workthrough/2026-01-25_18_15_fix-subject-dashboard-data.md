# 일반 유저 대시보드 실제 데이터 표시 수정

## 개요
일반 유저(subject role)가 로그인했을 때 본인의 테스트 데이터가 제대로 표시되지 않는 버그를 수정했습니다. API 응답 구조 불일치와 백엔드 역할(role) 체크 오류가 원인이었습니다.

## 주요 변경사항
- 수정한 것: SubjectDashboard에서 `test.summary.vo2_max_rel` → `test.vo2_max_rel`로 변경 (API 응답 구조에 맞춤)
- 수정한 것: 백엔드 role 체크 `"subject"` → `("user", "subject")` (DB에는 "user"로 저장됨)
- 수정한 것: 일반 유저 테스트 필터링 - 이전에는 전체 테스트 노출, 이제 본인 테스트만 표시

## 핵심 코드
```typescript
// 프론트엔드: API 응답 구조에 맞게 수정
// 변경 전
{latestTest.summary?.vo2_max_rel?.toFixed(1)}

// 변경 후
{latestTest.vo2_max_rel?.toFixed(1) || '-'}
```

```python
# 백엔드: role 체크 수정
# 변경 전
if current_user.role == "subject":

# 변경 후
if current_user.role in ("user", "subject"):
```

## 결과
- ✅ 프론트엔드 빌드 성공
- ✅ daseul.song@cpet.com 계정 생성 완료
- ✅ Song_Daseul 피험자와 연결됨

## 다음 단계
- 백엔드 서버 재시작하여 변경사항 적용
- 일반 유저 로그인 테스트 (VO2MAX: 71.1, HR MAX: 189 표시 확인)
- MetabolismPage에서도 동일한 데이터 접근 패턴 검토
