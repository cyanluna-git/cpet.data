# Scripts

현재 `main` 브랜치에서 활성으로 쓰는 스크립트는 채널 운영과 데이터 보조 유틸리티 중심입니다.

## Active Scripts

- `start_claude_channel.sh`: tmux 안에서 Claude Code + development channel 세션 시작
- `check_claude_channel.sh`: channel health, tmux 세션, 최근 jobs 확인
- `seed_demo_platform_validation.py`: 약 300명 synthetic cohort 기반 demo DB / published report / snapshot / feature set을 한 번에 재생성하는 플랫폼 검증용 시더
- `intake_real_cpet_golden_corpus.py`: PhysioNet 공개 CPET 데이터에서 작은 real golden corpus를 다운로드하고 curated subset / manifest를 생성
- `check_platform_readiness_demo.py`: seeded demo DB에 대해 dashboard/manage/explorer/report readiness를 자동 점검하고 gap 후보를 JSON으로 출력
- `test_upload.py`, `test_parsing.py`, `test_failed_file.py`, `test_db_save.py`: 서버/파이프라인 수동 점검용

## Archive

- `backups/`와 `fixtures/`는 과거 데이터 백업/복원 자료입니다.
- 일부 SQL/미러링 스크립트는 레거시 PostgreSQL/Supabase 운영 흔적으로 남아 있을 수 있습니다.
- 현재 v2 기본 경로는 SQLite 기반이므로 새 작업은 `server/`, `pipeline/`, `data/` 기준으로 진행합니다.

## Typical Ops

채널 세션 시작:

```bash
./scripts/start_claude_channel.sh
```

채널 상태 점검:

```bash
./scripts/check_claude_channel.sh
```

플랫폼 밀도 검증용 demo DB 재생성:

```bash
python scripts/seed_demo_platform_validation.py --reset
```

공개 CPET golden corpus intake:

```bash
python scripts/intake_real_cpet_golden_corpus.py --reset
```

빠른 smoke:

```bash
python scripts/intake_real_cpet_golden_corpus.py --reset --datasets actes
```

seeded demo readiness 점검:

```bash
python scripts/check_platform_readiness_demo.py --seed-if-missing
```
