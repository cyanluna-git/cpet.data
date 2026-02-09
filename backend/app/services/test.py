"""Test Service - CPET 테스트 관련 비즈니스 로직"""

import math
import os
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import pandas as pd
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BreathData, CPETTest, Subject
from app.schemas.test import (
    CPETTestCreate,
    CPETTestUpdate,
    ProtocolType,
    TimeSeriesRequest,
)
from app.services.cosmed_parser import COSMEDParser, ParsedCPETData, SubjectInfo
from app.services.data_validator import DataValidator
from app.services.metabolism_analysis import AnalysisConfig, MetabolismAnalyzer


class TestService:
    """CPET 테스트 CRUD 및 분석 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, test_id: UUID) -> Optional[CPETTest]:
        """테스트 ID로 조회"""
        result = await self.db.execute(
            select(CPETTest).where(CPETTest.test_id == test_id)
        )
        return result.scalar_one_or_none()

    async def get_with_breath_data(self, test_id: UUID) -> Optional[CPETTest]:
        """테스트와 호흡 데이터 함께 조회"""
        result = await self.db.execute(
            select(CPETTest)
            .options(selectinload(CPETTest.breath_data))
            .where(CPETTest.test_id == test_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        subject_id: Optional[UUID] = None,
    ) -> Tuple[List[CPETTest], int]:
        """테스트 목록 조회"""
        query = select(CPETTest)

        if subject_id:
            query = query.where(CPETTest.subject_id == subject_id)

        # 전체 개수
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 페이징
        query = query.order_by(desc(CPETTest.test_date))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        tests = list(result.scalars().all())

        return tests, total

    async def get_by_subject(self, subject_id: UUID) -> List[CPETTest]:
        """피험자의 모든 테스트 조회"""
        result = await self.db.execute(
            select(CPETTest)
            .where(CPETTest.subject_id == subject_id)
            .order_by(desc(CPETTest.test_date))
        )
        return list(result.scalars().all())

    async def get_latest_by_subject(self, subject_id: UUID) -> Optional[CPETTest]:
        """피험자의 최신 테스트 조회"""
        result = await self.db.execute(
            select(CPETTest)
            .where(CPETTest.subject_id == subject_id)
            .order_by(desc(CPETTest.test_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, data: CPETTestCreate) -> CPETTest:
        """테스트 생성"""
        test = CPETTest(
            subject_id=data.subject_id,
            test_date=data.test_date,
            test_time=data.test_time,
            protocol_name=data.protocol_name,
            protocol_type=data.protocol_type,
            test_type=data.test_type,
            notes=data.notes,
        )
        self.db.add(test)
        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def update(self, test_id: UUID, data: CPETTestUpdate) -> Optional[CPETTest]:
        """테스트 업데이트"""
        test = await self.get_by_id(test_id)
        if not test:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(test, field, value)

        test.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def delete(self, test_id: UUID) -> bool:
        """테스트 삭제 (cascade로 호흡 데이터도 삭제)"""
        test = await self.get_by_id(test_id)
        if not test:
            return False

        await self.db.delete(test)
        await self.db.commit()
        return True

    async def find_or_create_subject(
        self,
        subject_info: SubjectInfo,
    ) -> Tuple[Subject, bool]:
        """
        피험자 자동 매칭/생성

        매칭 우선순위:
        1. research_id 정확히 일치
        2. last_name + first_name으로 생성한 research_id 일치
        3. encrypted_name 일치

        없으면 새 피험자 생성

        Returns:
            (Subject, created: bool) - 생성 여부
        """
        # 이름 정리
        first_name = (subject_info.first_name or "").strip()
        last_name = (subject_info.last_name or "").strip()
        research_id = (subject_info.research_id or "").strip()

        # 이름 기반 research_id 생성 (형식: "LastName_FirstName")
        name_based_id = f"{last_name}_{first_name}" if last_name and first_name else ""
        # 대소문자 구분 없이 매칭용
        name_based_id_lower = name_based_id.lower()

        # encrypted_name (표시용 이름)
        full_name = f"{first_name} {last_name}".strip()

        # 1. research_id로 검색 (파일에서 추출된 ID가 있는 경우)
        if research_id:
            result = await self.db.execute(
                select(Subject).where(
                    func.lower(Subject.research_id) == research_id.lower()
                )
            )
            subject = result.scalar_one_or_none()
            if subject:
                return subject, False

        # 2. name_based_id로 검색
        if name_based_id:
            result = await self.db.execute(
                select(Subject).where(
                    func.lower(Subject.research_id) == name_based_id_lower
                )
            )
            subject = result.scalar_one_or_none()
            if subject:
                return subject, False

        # 3. encrypted_name으로 검색
        if full_name:
            result = await self.db.execute(
                select(Subject).where(
                    func.lower(Subject.encrypted_name) == full_name.lower()
                )
            )
            subject = result.scalar_one_or_none()
            if subject:
                return subject, False

        # 4. 매칭 실패 → 새 피험자 생성
        # research_id 결정: 파일의 research_id > name_based_id > "unknown_{timestamp}"
        final_research_id = (
            research_id
            or name_based_id
            or f"unknown_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )

        # 중복 방지: 이미 존재하면 숫자 suffix 추가
        base_id = final_research_id
        counter = 1
        while True:
            result = await self.db.execute(
                select(Subject).where(
                    func.lower(Subject.research_id) == final_research_id.lower()
                )
            )
            if result.scalar_one_or_none() is None:
                break
            final_research_id = f"{base_id}_{counter}"
            counter += 1

        # Gender 변환 (Male/Female → M/F)
        gender = None
        if subject_info.gender:
            g = subject_info.gender.strip().lower()
            if g in ("male", "m"):
                gender = "M"
            elif g in ("female", "f"):
                gender = "F"

        # birth_date 파싱
        birth_date = None
        birth_year = None
        if subject_info.birth_date:
            try:
                if isinstance(subject_info.birth_date, str):
                    birth_date = datetime.strptime(
                        subject_info.birth_date, "%m/%d/%Y"
                    ).date()
                    birth_year = birth_date.year
                else:
                    birth_date = subject_info.birth_date
                    birth_year = birth_date.year
            except Exception:
                pass

        # 새 피험자 생성
        new_subject = Subject(
            research_id=final_research_id,
            encrypted_name=full_name or None,
            birth_year=birth_year,
            birth_date=birth_date,
            gender=gender,
            height_cm=subject_info.height_cm,
            weight_kg=subject_info.weight_kg,
        )
        self.db.add(new_subject)
        # 피험자 생성 즉시 커밋 - 테스트 업로드 실패해도 피험자는 유지
        await self.db.commit()
        await self.db.refresh(new_subject)

        return new_subject, True

    async def upload_and_parse(
        self,
        file_content: bytes,
        filename: str,
        subject_id: UUID,
        calc_method: str = "Frayn",
        smoothing_window: int = 10,
    ) -> Tuple[CPETTest, List[str], List[str]]:
        """
        COSMED 파일 업로드 및 파싱

        Returns:
            (CPETTest, errors, warnings)
        """
        # 피험자 확인
        subject_result = await self.db.execute(
            select(Subject).where(Subject.id == subject_id)
        )
        subject = subject_result.scalar_one_or_none()
        if not subject:
            raise ValueError(f"Subject not found: {subject_id}")

        # 중복 테스트 체크 및 삭제 (같은 피험자 + 같은 파일명 = override)
        existing_test_result = await self.db.execute(
            select(CPETTest).where(
                CPETTest.subject_id == subject_id,
                CPETTest.source_filename == filename,
            )
        )
        existing_test = existing_test_result.scalar_one_or_none()
        if existing_test:
            # 기존 테스트의 BreathData 먼저 삭제
            await self.db.execute(
                delete(BreathData).where(BreathData.test_id == existing_test.test_id)
            )
            # 기존 테스트 삭제
            await self.db.delete(existing_test)
            await self.db.flush()
            print(f"[OVERRIDE] Deleted existing test: {existing_test.test_id}")

        # 임시 파일로 저장 후 파싱
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            parser = COSMEDParser()
            parsed_data = parser.parse_file(tmp_path)

            # Update subject information from parsed data if available
            if parsed_data.subject.birth_date and not subject.birth_date:
                try:
                    from datetime import datetime as dt

                    # Parse birth_date string to date object
                    if isinstance(parsed_data.subject.birth_date, str):
                        birth_date = dt.strptime(
                            parsed_data.subject.birth_date, "%m/%d/%Y"
                        ).date()
                    else:
                        birth_date = parsed_data.subject.birth_date
                    subject.birth_date = birth_date
                except Exception as e:
                    print(f"Failed to parse birth_date: {e}")

            # Update height and weight if not set
            if parsed_data.subject.height_cm and not subject.height_cm:
                subject.height_cm = parsed_data.subject.height_cm
            if parsed_data.subject.weight_kg and not subject.weight_kg:
                subject.weight_kg = parsed_data.subject.weight_kg

            await self.db.flush()

            # ========================================
            # DATA VALIDATION & PROTOCOL CLASSIFICATION
            # ========================================
            validator = DataValidator()
            validation_result = validator.validate(parsed_data.breath_data_df)

            # Log validation summary
            print(validator.get_validation_summary(validation_result))

            # 검증 실패 시 조기 반환 (데이터 저장은 하되 분석은 스킵)
            if not validation_result.is_valid:
                test = CPETTest(
                    subject_id=subject_id,
                    test_date=parsed_data.test.test_date or datetime.now(),
                    test_time=parsed_data.test.test_time,
                    protocol_name=parsed_data.test.protocol,
                    protocol_type=validation_result.protocol_type.value,
                    test_type=parsed_data.test.test_type or "Maximal",
                    source_filename=filename,
                    file_upload_timestamp=datetime.utcnow(),
                    parsing_status="validation_failed",
                    parsing_errors={
                        "validation_errors": validation_result.reason,
                        "quality_score": validation_result.quality_score,
                        "metadata": validation_result.metadata,
                    },
                    data_quality_score=validation_result.quality_score,
                )
                self.db.add(test)
                await self.db.commit()
                await self.db.refresh(test)

                errors = validation_result.reason
                warnings = ["Data validation failed - test saved but not analyzed"]
                return test, errors, warnings

            # 프로토콜 타입이 RAMP 또는 HYBRID가 아니면 분석 스킵
            if validation_result.protocol_type not in (
                ProtocolType.RAMP,
                ProtocolType.HYBRID,
            ):
                test = CPETTest(
                    subject_id=subject_id,
                    test_date=parsed_data.test.test_date or datetime.now(),
                    test_time=parsed_data.test.test_time,
                    protocol_name=parsed_data.test.protocol,
                    protocol_type=validation_result.protocol_type.value,
                    test_type=parsed_data.test.test_type or "Maximal",
                    source_filename=filename,
                    file_upload_timestamp=datetime.utcnow(),
                    parsing_status="skipped_protocol_mismatch",
                    parsing_errors={
                        "protocol_type": validation_result.protocol_type.value,
                        "reason": f"Protocol type {validation_result.protocol_type.value} is not suitable for standard analysis (FatMax/VT). Only RAMP or HYBRID protocols are supported.",
                        "quality_score": validation_result.quality_score,
                        "metadata": validation_result.metadata,
                    },
                    data_quality_score=validation_result.quality_score,
                )
                self.db.add(test)
                await self.db.flush()

                # BreathData는 저장 (나중에 다른 분석 가능)
                # BxB 데이터의 경우 같은 t_sec에 여러 데이터가 있을 수 있음
                # 중복 키 방지를 위해 t_sec 기준으로 그룹화하여 평균값 사용
                df_for_breath = parsed_data.breath_data_df.copy()
                if "t_sec" in df_for_breath.columns:
                    numeric_cols = df_for_breath.select_dtypes(
                        include=["number"]
                    ).columns.tolist()
                    agg_dict = {col: "mean" for col in numeric_cols if col != "t_sec"}
                    if agg_dict:
                        df_for_breath = df_for_breath.groupby(
                            "t_sec", as_index=False
                        ).agg(agg_dict)
                        df_for_breath = df_for_breath.sort_values("t_sec").reset_index(
                            drop=True
                        )

                base_time = test.test_date
                breath_batch = []
                for idx, row in df_for_breath.iterrows():
                    t_sec = row.get("t_sec") or row.get("t") or 0
                    timestamp = base_time + timedelta(seconds=float(t_sec))

                    breath = BreathData(
                        test_id=test.test_id,
                        time=timestamp,
                        t_sec=float(t_sec) if pd.notna(t_sec) else None,
                        vo2=float(row.get("vo2")) if pd.notna(row.get("vo2")) else None,
                        vco2=(
                            float(row.get("vco2"))
                            if pd.notna(row.get("vco2"))
                            else None
                        ),
                        hr=int(row.get("hr")) if pd.notna(row.get("hr")) else None,
                        bike_power=(
                            int(row.get("bike_power"))
                            if pd.notna(row.get("bike_power"))
                            else None
                        ),
                    )
                    breath_batch.append(breath)

                    if len(breath_batch) >= 100:
                        self.db.add_all(breath_batch)
                        await self.db.flush()
                        breath_batch = []

                if breath_batch:
                    self.db.add_all(breath_batch)

                await self.db.commit()
                await self.db.refresh(test)

                warnings = [
                    f"Protocol type {validation_result.protocol_type.value} detected - standard analysis skipped",
                    "Only raw data saved. RAMP protocol required for FatMax/VT analysis.",
                ]
                return test, [], warnings

            # ========================================
            # HYBRID 프로토콜 처리: 2개의 RAMP 구간을 분리 분석
            # ========================================
            if (
                validation_result.protocol_type == ProtocolType.HYBRID
                and validation_result.hybrid_phases
            ):
                hybrid_phases = validation_result.hybrid_phases
                print(f"[HYBRID] Detected hybrid protocol with phases:")
                if hybrid_phases.metabolic_phase:
                    print(
                        f"  - Metabolic phase: {hybrid_phases.metabolic_phase.start_sec}s ~ {hybrid_phases.metabolic_phase.end_sec}s"
                    )
                if hybrid_phases.recovery_phase:
                    print(
                        f"  - Recovery phase: {hybrid_phases.recovery_phase.start_sec}s ~ {hybrid_phases.recovery_phase.end_sec}s"
                    )
                if hybrid_phases.vo2max_phase:
                    print(
                        f"  - VO2max phase: {hybrid_phases.vo2max_phase.start_sec}s ~ {hybrid_phases.vo2max_phase.end_sec}s"
                    )

                # 전체 데이터에 대해 대사 지표 계산
                df_with_metrics = parser.calculate_metabolic_metrics(
                    parsed_data,
                    calc_method=calc_method,
                    smoothing_window=smoothing_window,
                )

                # Phase 1: 대사 분석용 데이터 (FatMax 계산)
                fatmax_metrics = {}
                vt_thresholds = {}
                if hybrid_phases.metabolic_phase:
                    metabolic_start = hybrid_phases.metabolic_phase.start_sec
                    metabolic_end = hybrid_phases.metabolic_phase.end_sec
                    df_metabolic = df_with_metrics[
                        (df_with_metrics["t_sec"] >= metabolic_start)
                        & (df_with_metrics["t_sec"] <= metabolic_end)
                    ].copy()

                    if len(df_metabolic) > 10:
                        # FatMax 분석
                        df_metabolic_phases = parser.detect_phases(df_metabolic)
                        fatmax_metrics = parser.find_fatmax(df_metabolic_phases)
                        # VT 역치 감지 (대사 구간에서)
                        vt_thresholds = parser.detect_ventilatory_thresholds(
                            df_metabolic_phases, method="v_slope"
                        )
                        print(
                            f"[HYBRID] Metabolic phase FatMax: {fatmax_metrics.get('fat_max_watt')}W"
                        )

                # Phase 2: VO2max 분석용 데이터
                vo2max_metrics = {}
                if hybrid_phases.vo2max_phase:
                    vo2max_start = hybrid_phases.vo2max_phase.start_sec
                    vo2max_end = hybrid_phases.vo2max_phase.end_sec
                    df_vo2max = df_with_metrics[
                        (df_with_metrics["t_sec"] >= vo2max_start)
                        & (df_with_metrics["t_sec"] <= vo2max_end)
                    ].copy()

                    if len(df_vo2max) > 10:
                        df_vo2max_phases = parser.detect_phases(df_vo2max)
                        vo2max_metrics = parser.find_vo2max(df_vo2max_phases)
                        print(
                            f"[HYBRID] VO2max phase metrics: VO2max={vo2max_metrics.get('vo2_max')}, HR_max={vo2max_metrics.get('hr_max')}"
                        )

                # 전체 데이터에 대해 phase 감지 (전체 구조 파악용)
                df_with_phases = parser.detect_phases(df_with_metrics)
                phase_boundaries = parser.get_phase_boundaries(df_with_phases)
                phase_metrics = parser.calculate_phase_metrics(df_with_phases)

                # HYBRID 분석 결과를 phase_metrics에 추가
                phase_metrics["hybrid_analysis"] = {
                    "metabolic_phase": (
                        {
                            "start_sec": hybrid_phases.metabolic_phase.start_sec,
                            "end_sec": hybrid_phases.metabolic_phase.end_sec,
                            "correlation": hybrid_phases.metabolic_phase.correlation,
                        }
                        if hybrid_phases.metabolic_phase
                        else None
                    ),
                    "recovery_phase": (
                        {
                            "start_sec": hybrid_phases.recovery_phase.start_sec,
                            "end_sec": hybrid_phases.recovery_phase.end_sec,
                        }
                        if hybrid_phases.recovery_phase
                        else None
                    ),
                    "vo2max_phase": (
                        {
                            "start_sec": hybrid_phases.vo2max_phase.start_sec,
                            "end_sec": hybrid_phases.vo2max_phase.end_sec,
                            "correlation": hybrid_phases.vo2max_phase.correlation,
                        }
                        if hybrid_phases.vo2max_phase
                        else None
                    ),
                }

                # CPETTest 생성 (HYBRID)
                test = CPETTest(
                    subject_id=subject_id,
                    test_date=parsed_data.test.test_date or datetime.now(),
                    test_time=parsed_data.test.test_time,
                    protocol_name=parsed_data.test.protocol,
                    protocol_type="HYBRID",  # HYBRID로 명시
                    test_type=parsed_data.test.test_type or "Maximal",
                    maximal_effort=parsed_data.test.maximal_effort,
                    test_duration=parsed_data.test.test_duration,
                    exercise_duration=parsed_data.test.exercise_duration,
                    barometric_pressure=parsed_data.environment.barometric_pressure,
                    ambient_temp=parsed_data.environment.ambient_temp,
                    ambient_humidity=parsed_data.environment.ambient_humidity,
                    device_temp=parsed_data.environment.device_temp,
                    age=parsed_data.subject.age,
                    height_cm=subject.height_cm or parsed_data.subject.height_cm,
                    weight_kg=subject.weight_kg or parsed_data.subject.weight_kg,
                    bsa=parsed_data.environment.bsa,
                    bmi=parsed_data.environment.bmi,
                    # VO2max 메트릭 (vo2max_phase에서)
                    vo2_max=vo2max_metrics.get("vo2_max"),
                    vo2_max_rel=vo2max_metrics.get("vo2_max_rel"),
                    vco2_max=vo2max_metrics.get("vco2_max"),
                    hr_max=vo2max_metrics.get("hr_max"),
                    # FatMax 메트릭 (metabolic_phase에서)
                    fat_max_hr=fatmax_metrics.get("fat_max_hr"),
                    fat_max_watt=fatmax_metrics.get("fat_max_watt"),
                    fat_max_g_min=fatmax_metrics.get("fat_max_g_min"),
                    # VT 역치 (metabolic_phase에서)
                    vt1_hr=vt_thresholds.get("vt1_hr"),
                    vt1_vo2=vt_thresholds.get("vt1_vo2"),
                    vt2_hr=vt_thresholds.get("vt2_hr"),
                    vt2_vo2=vt_thresholds.get("vt2_vo2"),
                    # 구간 경계 시간
                    warmup_end_sec=phase_boundaries.get("warmup_end_sec"),
                    test_end_sec=phase_boundaries.get("exercise_end_sec"),
                    calc_method=calc_method,
                    smoothing_window=smoothing_window,
                    source_filename=filename,
                    file_upload_timestamp=datetime.utcnow(),
                    parsing_status=(
                        "success" if not parsed_data.parsing_errors else "warning"
                    ),
                    parsing_errors=(
                        {"errors": parsed_data.parsing_errors}
                        if parsed_data.parsing_errors
                        else None
                    ),
                    data_quality_score=validation_result.quality_score,
                    phase_metrics=phase_metrics if phase_metrics else None,
                )
                self.db.add(test)
                await self.db.flush()

                # BreathData 저장 로직은 RAMP와 동일
                # (아래 코드 블록으로 점프 - goto 없으므로 공통 함수로 분리 필요)
                # 지금은 코드 중복으로 처리
                base_time = test.test_date
                breath_batch = []
                batch_size = 100

                if "t_sec" in df_with_phases.columns:
                    numeric_cols = df_with_phases.select_dtypes(
                        include=["number"]
                    ).columns.tolist()
                    non_numeric_cols = [
                        c
                        for c in df_with_phases.columns
                        if c not in numeric_cols and c != "t_sec"
                    ]
                    agg_dict = {col: "mean" for col in numeric_cols if col != "t_sec"}
                    for col in non_numeric_cols:
                        agg_dict[col] = "first"
                    if agg_dict:
                        df_with_phases = df_with_phases.groupby(
                            "t_sec", as_index=False
                        ).agg(agg_dict)
                        df_with_phases = df_with_phases.sort_values(
                            "t_sec"
                        ).reset_index(drop=True)

                for idx, row in df_with_phases.iterrows():
                    t_sec = row.get("t_sec", idx)
                    if t_sec is None or (isinstance(t_sec, float) and t_sec != t_sec):
                        t_sec = float(idx)

                    def safe_get(key, convert_type=None):
                        val = row.get(key)
                        if val is None:
                            return None
                        if isinstance(val, float):
                            if math.isnan(val) or math.isinf(val):
                                return None
                        if convert_type == int and val is not None:
                            try:
                                return int(val)
                            except (ValueError, TypeError):
                                return None
                        return val

                    breath = BreathData(
                        time=base_time + timedelta(seconds=float(t_sec)),
                        test_id=test.test_id,
                        t_sec=t_sec,
                        rf=safe_get("rf"),
                        vt=safe_get("vt"),
                        vo2=safe_get("vo2"),
                        vco2=safe_get("vco2"),
                        ve=safe_get("ve"),
                        hr=safe_get("hr", int),
                        vo2_hr=safe_get("vo2_hr"),
                        bike_power=safe_get("bike_power", int),
                        bike_torque=safe_get("bike_torque"),
                        cadence=safe_get("cadence", int),
                        feo2=safe_get("feo2"),
                        feco2=safe_get("feco2"),
                        feto2=safe_get("feto2"),
                        fetco2=safe_get("fetco2"),
                        ve_vo2=safe_get("ve_vo2"),
                        ve_vco2=safe_get("ve_vco2"),
                        rer=safe_get("rer"),
                        fat_oxidation=safe_get("fat_oxidation"),
                        cho_oxidation=safe_get("cho_oxidation"),
                        vo2_rel=safe_get("vo2_rel"),
                        mets=safe_get("mets"),
                        ee_total=safe_get("ee_total_calc"),
                        phase=safe_get("phase"),
                        data_source=parsed_data.protocol_type,
                        is_valid=True,
                    )
                    breath_batch.append(breath)

                    if len(breath_batch) >= batch_size:
                        self.db.add_all(breath_batch)
                        await self.db.flush()
                        breath_batch = []

                if breath_batch:
                    self.db.add_all(breath_batch)
                    await self.db.flush()

                await self.db.commit()
                await self.db.refresh(test)

                del df_with_phases
                del df_with_metrics

                return test, parsed_data.parsing_errors, parsed_data.parsing_warnings

            # ========================================
            # PROCEED WITH STANDARD ANALYSIS (RAMP)
            # ========================================

            # 대사 지표 계산
            df_with_metrics = parser.calculate_metabolic_metrics(
                parsed_data,
                calc_method=calc_method,
                smoothing_window=smoothing_window,
            )

            # 구간 감지 (Phase Detection)
            df_with_phases = parser.detect_phases(df_with_metrics)

            # 구간 경계 및 메트릭 계산
            phase_boundaries = parser.get_phase_boundaries(df_with_phases)
            phase_metrics = parser.calculate_phase_metrics(df_with_phases)

            # VO2MAX, FATMAX 찾기
            vo2max_metrics = parser.find_vo2max(df_with_phases)
            fatmax_metrics = parser.find_fatmax(df_with_phases)

            # VT1/VT2 역치 감지
            vt_thresholds = parser.detect_ventilatory_thresholds(
                df_with_phases, method="v_slope"
            )

            # CPETTest 생성
            test = CPETTest(
                subject_id=subject_id,
                test_date=parsed_data.test.test_date or datetime.now(),
                test_time=parsed_data.test.test_time,
                protocol_name=parsed_data.test.protocol,
                protocol_type=parsed_data.protocol_type,
                test_type=parsed_data.test.test_type or "Maximal",
                maximal_effort=parsed_data.test.maximal_effort,
                test_duration=parsed_data.test.test_duration,
                exercise_duration=parsed_data.test.exercise_duration,
                barometric_pressure=parsed_data.environment.barometric_pressure,
                ambient_temp=parsed_data.environment.ambient_temp,
                ambient_humidity=parsed_data.environment.ambient_humidity,
                device_temp=parsed_data.environment.device_temp,
                age=parsed_data.subject.age,
                height_cm=subject.height_cm or parsed_data.subject.height_cm,
                weight_kg=subject.weight_kg or parsed_data.subject.weight_kg,
                bsa=parsed_data.environment.bsa,
                bmi=parsed_data.environment.bmi,
                vo2_max=vo2max_metrics.get("vo2_max"),
                vo2_max_rel=vo2max_metrics.get("vo2_max_rel"),
                vco2_max=vo2max_metrics.get("vco2_max"),
                hr_max=vo2max_metrics.get("hr_max"),
                fat_max_hr=fatmax_metrics.get("fat_max_hr"),
                fat_max_watt=fatmax_metrics.get("fat_max_watt"),
                fat_max_g_min=fatmax_metrics.get("fat_max_g_min"),
                # VT 역치 추가
                vt1_hr=vt_thresholds.get("vt1_hr"),
                vt1_vo2=vt_thresholds.get("vt1_vo2"),
                vt2_hr=vt_thresholds.get("vt2_hr"),
                vt2_vo2=vt_thresholds.get("vt2_vo2"),
                # 구간 경계 시간 추가
                warmup_end_sec=phase_boundaries.get("warmup_end_sec"),
                test_end_sec=phase_boundaries.get("exercise_end_sec"),
                calc_method=calc_method,
                smoothing_window=smoothing_window,
                source_filename=filename,
                file_upload_timestamp=datetime.utcnow(),
                parsing_status=(
                    "success" if not parsed_data.parsing_errors else "warning"
                ),
                parsing_errors=(
                    {"errors": parsed_data.parsing_errors}
                    if parsed_data.parsing_errors
                    else None
                ),
                data_quality_score=validation_result.quality_score,
                # 구간별 메트릭 저장 (JSON)
                phase_metrics=phase_metrics if phase_metrics else None,
            )
            self.db.add(test)
            await self.db.flush()

            # BreathData 생성 (phase 정보 포함) - 배치 처리
            base_time = test.test_date
            breath_batch = []
            batch_size = 100  # 100개씩 배치 처리

            # BxB 데이터의 경우 같은 t_sec에 여러 데이터가 있을 수 있음
            # 중복 키 방지를 위해 t_sec 기준으로 그룹화하여 평균값 사용
            if "t_sec" in df_with_phases.columns:
                # 숫자 컬럼만 평균, 문자열 컬럼은 첫 번째 값 사용
                numeric_cols = df_with_phases.select_dtypes(
                    include=["number"]
                ).columns.tolist()
                non_numeric_cols = [
                    c
                    for c in df_with_phases.columns
                    if c not in numeric_cols and c != "t_sec"
                ]

                agg_dict = {col: "mean" for col in numeric_cols if col != "t_sec"}
                for col in non_numeric_cols:
                    agg_dict[col] = "first"

                if agg_dict:
                    df_with_phases = df_with_phases.groupby(
                        "t_sec", as_index=False
                    ).agg(agg_dict)
                    df_with_phases = df_with_phases.sort_values("t_sec").reset_index(
                        drop=True
                    )

            for idx, row in df_with_phases.iterrows():
                t_sec = row.get("t_sec", idx)
                if t_sec is None or (
                    isinstance(t_sec, float) and t_sec != t_sec
                ):  # NaN check
                    t_sec = float(idx)

                # Helper function to safely get values and convert NaN to None
                def safe_get(key, convert_type=None):
                    val = row.get(key)
                    if val is None:
                        return None
                    # Check for NaN or Inf
                    if isinstance(val, float):
                        if math.isnan(val) or math.isinf(val):
                            return None
                    if convert_type == int and val is not None:
                        try:
                            return int(val)
                        except (ValueError, TypeError):
                            return None
                    return val

                breath = BreathData(
                    time=base_time + timedelta(seconds=float(t_sec)),
                    test_id=test.test_id,
                    t_sec=t_sec,
                    rf=safe_get("rf"),
                    vt=safe_get("vt"),
                    vo2=safe_get("vo2"),
                    vco2=safe_get("vco2"),
                    ve=safe_get("ve"),
                    hr=safe_get("hr", int),
                    vo2_hr=safe_get("vo2_hr"),
                    bike_power=safe_get("bike_power", int),
                    bike_torque=safe_get("bike_torque"),
                    cadence=safe_get("cadence", int),
                    feo2=safe_get("feo2"),
                    feco2=safe_get("feco2"),
                    feto2=safe_get("feto2"),
                    fetco2=safe_get("fetco2"),
                    ve_vo2=safe_get("ve_vo2"),
                    ve_vco2=safe_get("ve_vco2"),
                    rer=safe_get("rer"),
                    fat_oxidation=safe_get("fat_oxidation"),
                    cho_oxidation=safe_get("cho_oxidation"),
                    vo2_rel=safe_get("vo2_rel"),
                    mets=safe_get("mets"),
                    ee_total=safe_get("ee_total_calc"),
                    phase=safe_get("phase"),  # 자동 감지된 구간
                    data_source=parsed_data.protocol_type,
                    is_valid=True,
                )
                breath_batch.append(breath)

                # 배치 크기에 도달하면 flush
                if len(breath_batch) >= batch_size:
                    try:
                        self.db.add_all(breath_batch)
                        await self.db.flush()
                    except Exception as e:
                        print(f"[ERROR] Batch flush failed at idx {idx}: {e}")
                        raise
                    breath_batch = []

            # 남은 데이터 flush
            if breath_batch:
                try:
                    self.db.add_all(breath_batch)
                    await self.db.flush()
                except Exception as e:
                    print(f"[ERROR] Final batch flush failed: {e}")
                    raise

            try:
                await self.db.commit()
                await self.db.refresh(test)
            except Exception as e:
                print(f"[ERROR] Commit failed: {e}")
                raise

            # DataFrame 메모리 해제
            del df_with_phases
            del df_with_metrics

            return test, parsed_data.parsing_errors, parsed_data.parsing_warnings

        finally:
            os.unlink(tmp_path)

    async def get_raw_breath_data(self, test_id: UUID) -> List[BreathData]:
        """Raw breath data 전체 조회 (데이터 분석용)"""
        query = (
            select(BreathData)
            .where(BreathData.test_id == test_id)
            .order_by(BreathData.t_sec)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_time_series(
        self,
        test_id: UUID,
        request: TimeSeriesRequest,
    ) -> Dict[str, Any]:
        """시계열 데이터 조회 (다운샘플링 지원)"""
        # 기본 쿼리
        query = select(BreathData).where(BreathData.test_id == test_id)

        # 시간 범위 필터
        if request.start_sec is not None:
            query = query.where(BreathData.t_sec >= request.start_sec)
        if request.end_sec is not None:
            query = query.where(BreathData.t_sec <= request.end_sec)

        query = query.order_by(BreathData.t_sec)

        result = await self.db.execute(query)
        breath_data = list(result.scalars().all())

        if not breath_data:
            return {
                "test_id": test_id,
                "signals": request.signals,
                "interval": request.interval,
                "data_points": [],
                "total_points": 0,
                "duration_sec": 0,
            }

        # 다운샘플링 간격 파싱 (예: "1s" -> 1초)
        interval_sec = int(request.interval.rstrip("s"))

        # 데이터 포인트 변환
        data_points = []
        current_bucket = []
        bucket_start = breath_data[0].t_sec or 0

        for bd in breath_data:
            t_sec = bd.t_sec or 0
            if t_sec < bucket_start + interval_sec:
                current_bucket.append(bd)
            else:
                # 현재 버킷 집계
                if current_bucket:
                    point = self._aggregate_bucket(
                        current_bucket, request.signals, request.method, bucket_start
                    )
                    data_points.append(point)

                # 새 버킷 시작
                bucket_start = (int(t_sec / interval_sec)) * interval_sec
                current_bucket = [bd]

        # 마지막 버킷 처리
        if current_bucket:
            point = self._aggregate_bucket(
                current_bucket, request.signals, request.method, bucket_start
            )
            data_points.append(point)

        # 전체 시간 계산
        duration_sec = (breath_data[-1].t_sec or 0) - (breath_data[0].t_sec or 0)

        return {
            "test_id": test_id,
            "signals": request.signals,
            "interval": request.interval,
            "data_points": data_points,
            "total_points": len(data_points),
            "duration_sec": duration_sec,
        }

    def _aggregate_bucket(
        self,
        bucket: List[BreathData],
        signals: List[str],
        method: str,
        bucket_start: float,
    ) -> Dict[str, Any]:
        """버킷 데이터 집계"""
        point = {"t_sec": bucket_start}

        for signal in signals:
            values = []
            for bd in bucket:
                val = getattr(bd, signal, None)
                if val is not None:
                    values.append(val)

            if values:
                if method == "mean":
                    point[signal] = sum(values) / len(values)
                elif method == "median":
                    sorted_vals = sorted(values)
                    mid = len(sorted_vals) // 2
                    point[signal] = sorted_vals[mid]
                elif method == "max":
                    point[signal] = max(values)
                elif method == "min":
                    point[signal] = min(values)
            else:
                point[signal] = None

        return point

    async def get_metrics(self, test_id: UUID) -> Dict[str, Any]:
        """테스트 메트릭 요약 조회"""
        test = await self.get_by_id(test_id)
        if not test:
            return {}

        # 페이즈별 통계
        phases_query = (
            select(
                BreathData.phase,
                func.min(BreathData.t_sec).label("start_sec"),
                func.max(BreathData.t_sec).label("end_sec"),
                func.count().label("count"),
            )
            .where(
                and_(
                    BreathData.test_id == test_id,
                    BreathData.phase.isnot(None),
                )
            )
            .group_by(BreathData.phase)
        )

        phases_result = await self.db.execute(phases_query)
        phases = {}
        for row in phases_result:
            phases[row.phase] = {
                "start_sec": row.start_sec,
                "end_sec": row.end_sec,
                "count": row.count,
            }

        # 테스트 시간
        duration_query = select(
            func.min(BreathData.t_sec).label("start"),
            func.max(BreathData.t_sec).label("end"),
        ).where(BreathData.test_id == test_id)
        duration_result = await self.db.execute(duration_query)
        duration_row = duration_result.first()

        test_duration_sec = None
        if (
            duration_row
            and duration_row.start is not None
            and duration_row.end is not None
        ):
            test_duration_sec = duration_row.end - duration_row.start

        return {
            "test_id": test.test_id,
            "subject_id": test.subject_id,
            "vo2_max": test.vo2_max,
            "vo2_max_rel": test.vo2_max_rel,
            "vo2_at_vt1": test.vt1_vo2,
            "vo2_at_vt2": test.vt2_vo2,
            "hr_max": test.hr_max,
            "hr_at_vt1": test.vt1_hr,
            "hr_at_vt2": test.vt2_hr,
            "vco2_max": test.vco2_max,
            "fat_max_hr": test.fat_max_hr,
            "fat_max_watt": test.fat_max_watt,
            "fat_max_g_min": test.fat_max_g_min,
            "test_duration_sec": test_duration_sec,
            "phases": phases,
        }

    async def get_tests_for_cohort(
        self,
        subject_ids: List[UUID],
        metric_names: List[str],
    ) -> List[Dict[str, Any]]:
        """코호트 분석용 테스트 데이터 조회"""
        if not subject_ids:
            return []

        # 각 피험자의 최신 테스트만 조회
        query = (
            select(CPETTest)
            .where(CPETTest.subject_id.in_(subject_ids))
            .order_by(CPETTest.subject_id, desc(CPETTest.test_date))
        )

        result = await self.db.execute(query)
        all_tests = list(result.scalars().all())

        # 피험자별 최신 테스트만 필터링
        latest_tests = {}
        for test in all_tests:
            if test.subject_id not in latest_tests:
                latest_tests[test.subject_id] = test

        # 메트릭 추출
        data = []
        for test in latest_tests.values():
            row = {"test_id": test.test_id, "subject_id": test.subject_id}
            for metric in metric_names:
                row[metric] = getattr(test, metric, None)
            data.append(row)

        return data

    async def get_analysis(
        self,
        test_id: UUID,
        interval: str = "5s",
        include_processed: bool = True,
        loess_frac: float = 0.25,
        bin_size: int = 10,
        aggregation_method: str = "median",
        min_power_threshold: Optional[int] = None,
        trim_start_sec: Optional[float] = None,
        trim_end_sec: Optional[float] = None,
        vo2max_start_sec: Optional[float] = None,
        vo2max_end_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        테스트 분석 결과 조회 (대사 프로파일 차트용)

        Args:
            test_id: 테스트 ID
            interval: 다운샘플 간격 (예: "5s")
            include_processed: LOESS/binning 처리 데이터 포함 여부
            loess_frac: LOESS smoothing fraction (0.1~0.5)
            bin_size: Power binning 크기 (W, 5~30)
            aggregation_method: 집계 방법 (median, mean, trimmed_mean)
            min_power_threshold: 최소 파워 임계값 (W, 이하 데이터 제외)
            trim_start_sec: Manual trim start time (seconds, optional)
            trim_end_sec: Manual trim end time (seconds, optional)
            vo2max_start_sec: VO2max segment start time (seconds, optional)
            vo2max_end_sec: VO2max segment end time (seconds, optional)

        Returns:
            - phase_boundaries: 구간 경계
            - phase_metrics: 구간별 메트릭
            - fatmax: FATMAX 정보
            - vo2max: VO2MAX 정보
            - timeseries: 다운샘플된 시계열 데이터
            - 통계 요약
            - processed_series: 처리된 대사 데이터
            - metabolic_markers: FatMax/Crossover 마커
            - used_trim_range: Applied trimming range (auto or manual)
        """
        test = await self.get_by_id(test_id)
        if not test:
            return {}

        # 모든 호흡 데이터 조회
        query = (
            select(BreathData)
            .where(BreathData.test_id == test_id)
            .order_by(BreathData.t_sec)
        )

        result = await self.db.execute(query)
        breath_data = list(result.scalars().all())

        if not breath_data:
            return {
                "test_id": test_id,
                "subject_id": test.subject_id,
                "test_date": test.test_date,
                "error": "No breath data found",
            }

        # Calculate total duration for frontend slider
        total_duration_sec = (
            breath_data[-1].t_sec if breath_data and breath_data[-1].t_sec else 0
        )

        # 구간 경계 계산
        phase_boundaries = self._calculate_phase_boundaries(breath_data)

        # 구간별 메트릭 계산
        phase_metrics = self._calculate_phase_metrics(breath_data)

        # FATMAX 정보
        fatmax_info = self._find_fatmax_info(breath_data, test)

        # VO2MAX 정보
        vo2max_info = self._find_vo2max_info(breath_data, test)

        # 시계열 다운샘플링 (차트용)
        interval_sec = int(interval.rstrip("s"))
        timeseries = self._downsample_for_chart(breath_data, interval_sec)

        # 총 연소량 계산
        total_fat_g = (
            sum(bd.fat_oxidation for bd in breath_data if bd.fat_oxidation is not None)
            / 60
        )  # g/min → g (assuming 1 data point per second)

        total_cho_g = (
            sum(bd.cho_oxidation for bd in breath_data if bd.cho_oxidation is not None)
            / 60
        )

        # 평균 RER (Exercise 구간만)
        exercise_rers = [
            bd.rer
            for bd in breath_data
            if bd.rer is not None and bd.phase == "Exercise"
        ]
        avg_rer = sum(exercise_rers) / len(exercise_rers) if exercise_rers else None

        # 운동 시간
        exercise_duration = None
        if phase_boundaries.get("phases"):
            for p in phase_boundaries["phases"]:
                if p["phase"] == "Exercise":
                    exercise_duration = p["end_sec"] - p["start_sec"]
                    break

        # 처리된 대사 데이터 분석 (LOESS smoothing, binning, markers)
        processed_series = None
        metabolic_markers = None
        analysis_warnings = None
        used_trim_range = None

        if include_processed:
            # Build AnalysisConfig with trim parameters
            config = AnalysisConfig(
                loess_frac=loess_frac,
                bin_size=max(5, min(30, bin_size)),
                aggregation_method=(
                    aggregation_method
                    if aggregation_method in ("median", "mean", "trimmed_mean")
                    else "median"
                ),
                min_power_threshold=min_power_threshold,
                # Trim parameters
                auto_trim_enabled=True,
                trim_start_sec=trim_start_sec,
                trim_end_sec=trim_end_sec,
                # v1.2.0: VO2max segment window (HYBRID protocol)
                vo2max_start_sec=vo2max_start_sec,
                vo2max_end_sec=vo2max_end_sec,
            )

            analyzer = MetabolismAnalyzer(config=config)

            analysis_result = analyzer.analyze(breath_data)
            if analysis_result:
                processed_series = analysis_result.processed_series.to_dict()
                metabolic_markers = analysis_result.metabolic_markers.to_dict()
                analysis_warnings = (
                    analysis_result.warnings if analysis_result.warnings else None
                )
                # Extract trim range for frontend
                if analysis_result.trim_range:
                    used_trim_range = analysis_result.trim_range.to_dict()

        return {
            "test_id": test_id,
            "subject_id": test.subject_id,
            "test_date": test.test_date,
            "protocol_type": test.protocol_type,
            "calc_method": test.calc_method,
            "phase_boundaries": phase_boundaries,
            "phase_metrics": phase_metrics,
            "fatmax": fatmax_info,
            "vo2max": vo2max_info,
            "vt1_hr": test.vt1_hr,
            "vt1_vo2": test.vt1_vo2,
            "vt2_hr": test.vt2_hr,
            "vt2_vo2": test.vt2_vo2,
            "timeseries": timeseries,
            "timeseries_interval": interval,
            "total_fat_burned_g": round(total_fat_g, 2) if total_fat_g else None,
            "total_cho_burned_g": round(total_cho_g, 2) if total_cho_g else None,
            "avg_rer": round(avg_rer, 3) if avg_rer else None,
            "exercise_duration_sec": exercise_duration,
            "processed_series": processed_series,
            "metabolic_markers": metabolic_markers,
            "analysis_warnings": analysis_warnings,
            "used_trim_range": used_trim_range,
            "total_duration_sec": total_duration_sec,
        }

    def _calculate_phase_boundaries(
        self, breath_data: List[BreathData]
    ) -> Dict[str, Any]:
        """구간 경계 계산"""
        boundaries = {
            "rest_end_sec": None,
            "warmup_end_sec": None,
            "exercise_end_sec": None,
            "peak_sec": None,
            "total_duration_sec": breath_data[-1].t_sec if breath_data else 0,
            "phases": [],
        }

        current_phase = None
        phase_start = None

        for bd in breath_data:
            if bd.phase != current_phase:
                # 이전 구간 종료
                if current_phase is not None and phase_start is not None:
                    boundaries["phases"].append(
                        {
                            "phase": current_phase,
                            "start_sec": phase_start,
                            "end_sec": bd.t_sec or 0,
                        }
                    )

                    if current_phase == "Rest":
                        boundaries["rest_end_sec"] = bd.t_sec
                    elif current_phase == "Warm-up":
                        boundaries["warmup_end_sec"] = bd.t_sec
                    elif current_phase == "Exercise":
                        boundaries["exercise_end_sec"] = bd.t_sec

                current_phase = bd.phase
                phase_start = bd.t_sec

                if bd.phase == "Peak":
                    boundaries["peak_sec"] = bd.t_sec

        # 마지막 구간
        if current_phase is not None and phase_start is not None:
            boundaries["phases"].append(
                {
                    "phase": current_phase,
                    "start_sec": phase_start,
                    "end_sec": breath_data[-1].t_sec if breath_data else 0,
                }
            )

        return boundaries

    def _calculate_phase_metrics(
        self, breath_data: List[BreathData]
    ) -> Dict[str, Dict]:
        """구간별 메트릭 계산"""
        phases_data = {}
        for bd in breath_data:
            phase = bd.phase or "Unknown"
            if phase not in phases_data:
                phases_data[phase] = []
            phases_data[phase].append(bd)

        metrics = {}
        for phase, data in phases_data.items():
            hrs = [bd.hr for bd in data if bd.hr]
            vo2s = [bd.vo2 for bd in data if bd.vo2]
            rers = [bd.rer for bd in data if bd.rer]
            fats = [bd.fat_oxidation for bd in data if bd.fat_oxidation]
            chos = [bd.cho_oxidation for bd in data if bd.cho_oxidation]
            powers = [bd.bike_power for bd in data if bd.bike_power]
            t_secs = [bd.t_sec for bd in data if bd.t_sec is not None]

            metrics[phase] = {
                "duration_sec": max(t_secs) - min(t_secs) if t_secs else 0,
                "data_points": len(data),
                "avg_hr": sum(hrs) / len(hrs) if hrs else None,
                "max_hr": max(hrs) if hrs else None,
                "avg_vo2": sum(vo2s) / len(vo2s) if vo2s else None,
                "max_vo2": max(vo2s) if vo2s else None,
                "avg_rer": sum(rers) / len(rers) if rers else None,
                "max_rer": max(rers) if rers else None,
                "avg_fat_oxidation": sum(fats) / len(fats) if fats else None,
                "max_fat_oxidation": max(fats) if fats else None,
                "avg_cho_oxidation": sum(chos) / len(chos) if chos else None,
                "max_cho_oxidation": max(chos) if chos else None,
                "avg_bike_power": sum(powers) / len(powers) if powers else None,
                "max_bike_power": max(powers) if powers else None,
            }

        return metrics

    def _find_fatmax_info(
        self, breath_data: List[BreathData], test: CPETTest
    ) -> Dict[str, Any]:
        """FATMAX 상세 정보"""
        fatmax_bd = max(
            (bd for bd in breath_data if bd.fat_oxidation is not None),
            key=lambda x: x.fat_oxidation,
            default=None,
        )

        if not fatmax_bd:
            return {}

        return {
            "fat_max_g_min": fatmax_bd.fat_oxidation,
            "fat_max_hr": fatmax_bd.hr or test.fat_max_hr,
            "fat_max_watt": fatmax_bd.bike_power or test.fat_max_watt,
            "fat_max_vo2": fatmax_bd.vo2,
            "fat_max_rer": fatmax_bd.rer,
            "fat_max_time_sec": fatmax_bd.t_sec,
        }

    def _find_vo2max_info(
        self, breath_data: List[BreathData], test: CPETTest
    ) -> Dict[str, Any]:
        """VO2MAX 상세 정보"""
        vo2max_bd = max(
            (bd for bd in breath_data if bd.vo2 is not None),
            key=lambda x: x.vo2,
            default=None,
        )

        if not vo2max_bd:
            return {}

        return {
            "vo2_max": vo2max_bd.vo2 or test.vo2_max,
            "vo2_max_rel": vo2max_bd.vo2_rel or test.vo2_max_rel,
            "vco2_max": vo2max_bd.vco2 or test.vco2_max,
            "hr_max": max((bd.hr for bd in breath_data if bd.hr), default=None)
            or test.hr_max,
            "rer_at_max": vo2max_bd.rer,
            "vo2_max_time_sec": vo2max_bd.t_sec,
        }

    def _downsample_for_chart(
        self, breath_data: List[BreathData], interval_sec: int = 5
    ) -> List[Dict[str, Any]]:
        """차트용 다운샘플링 (with kcal/day 환산)"""
        if not breath_data:
            return []

        result = []
        bucket = []
        bucket_start = breath_data[0].t_sec or 0

        for bd in breath_data:
            t = bd.t_sec or 0
            if t < bucket_start + interval_sec:
                bucket.append(bd)
            else:
                if bucket:
                    result.append(self._aggregate_for_chart(bucket, bucket_start))
                bucket_start = (int(t / interval_sec)) * interval_sec
                bucket = [bd]

        if bucket:
            result.append(self._aggregate_for_chart(bucket, bucket_start))

        return result

    def _aggregate_for_chart(
        self, bucket: List[BreathData], bucket_start: float
    ) -> Dict[str, Any]:
        """차트용 버킷 집계 (with kcal/day 환산)"""

        def avg(vals):
            valid = [v for v in vals if v is not None]
            return sum(valid) / len(valid) if valid else None

        fat_ox = avg([bd.fat_oxidation for bd in bucket])
        cho_ox = avg([bd.cho_oxidation for bd in bucket])

        # g/min → kcal/day 환산
        # Fat: 9.75 kcal/g, CHO: 4.07 kcal/g
        # kcal/min * 60 * 24 = kcal/day
        fat_kcal_day = fat_ox * 9.75 * 60 * 24 if fat_ox else None
        cho_kcal_day = cho_ox * 4.07 * 60 * 24 if cho_ox else None

        # 가장 많이 나타나는 phase
        phases = [bd.phase for bd in bucket if bd.phase]
        phase = max(set(phases), key=phases.count) if phases else None

        return {
            "time_sec": bucket_start,
            "power": avg([bd.bike_power for bd in bucket]),
            "hr": (
                int(avg([bd.hr for bd in bucket]))
                if avg([bd.hr for bd in bucket])
                else None
            ),
            "vo2": avg([bd.vo2 for bd in bucket]),
            "vco2": avg([bd.vco2 for bd in bucket]),
            "rer": (
                round(avg([bd.rer for bd in bucket]), 3)
                if avg([bd.rer for bd in bucket])
                else None
            ),
            "fat_oxidation": round(fat_ox, 4) if fat_ox else None,
            "cho_oxidation": round(cho_ox, 4) if cho_ox else None,
            "fat_kcal_day": round(fat_kcal_day, 1) if fat_kcal_day else None,
            "cho_kcal_day": round(cho_kcal_day, 1) if cho_kcal_day else None,
            "phase": phase,
        }
