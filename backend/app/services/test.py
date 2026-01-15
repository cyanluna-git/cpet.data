"""Test Service - CPET 테스트 관련 비즈니스 로직"""

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID
import tempfile
import os

from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CPETTest, BreathData, Subject
from app.schemas.test import CPETTestCreate, CPETTestUpdate, TimeSeriesRequest
from app.services.cosmed_parser import COSMEDParser, ParsedCPETData


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

    async def update(
        self, test_id: UUID, data: CPETTestUpdate
    ) -> Optional[CPETTest]:
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

        # 임시 파일로 저장 후 파싱
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            parser = COSMEDParser()
            parsed_data = parser.parse_file(tmp_path)

            # 대사 지표 계산
            df_with_metrics = parser.calculate_metabolic_metrics(
                parsed_data,
                calc_method=calc_method,
                smoothing_window=smoothing_window,
            )

            # VO2MAX, FATMAX 찾기
            vo2max_metrics = parser.find_vo2max(df_with_metrics)
            fatmax_metrics = parser.find_fatmax(df_with_metrics)

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
                weight_kg=parsed_data.subject.weight_kg or subject.weight_kg,
                bsa=parsed_data.environment.bsa,
                bmi=parsed_data.environment.bmi,
                vo2_max=vo2max_metrics.get("vo2_max"),
                vo2_max_rel=vo2max_metrics.get("vo2_max_rel"),
                vco2_max=vo2max_metrics.get("vco2_max"),
                hr_max=vo2max_metrics.get("hr_max"),
                fat_max_hr=fatmax_metrics.get("fat_max_hr"),
                fat_max_watt=fatmax_metrics.get("fat_max_watt"),
                fat_max_g_min=fatmax_metrics.get("fat_max_g_min"),
                calc_method=calc_method,
                smoothing_window=smoothing_window,
                source_filename=filename,
                file_upload_timestamp=datetime.utcnow(),
                parsing_status="success" if not parsed_data.parsing_errors else "warning",
                parsing_errors={"errors": parsed_data.parsing_errors} if parsed_data.parsing_errors else None,
            )
            self.db.add(test)
            await self.db.flush()

            # BreathData 생성
            base_time = test.test_date
            for idx, row in df_with_metrics.iterrows():
                t_sec = row.get("t_sec", idx)
                if t_sec is None or (isinstance(t_sec, float) and t_sec != t_sec):  # NaN check
                    t_sec = float(idx)

                breath = BreathData(
                    time=base_time + timedelta(seconds=float(t_sec)),
                    test_id=test.test_id,
                    t_sec=t_sec,
                    rf=row.get("rf"),
                    vt=row.get("vt"),
                    vo2=row.get("vo2"),
                    vco2=row.get("vco2"),
                    ve=row.get("ve"),
                    hr=int(row.get("hr")) if row.get("hr") and not (row.get("hr") != row.get("hr")) else None,
                    vo2_hr=row.get("vo2_hr"),
                    bike_power=int(row.get("bike_power")) if row.get("bike_power") and not (row.get("bike_power") != row.get("bike_power")) else None,
                    bike_torque=row.get("bike_torque"),
                    cadence=int(row.get("cadence")) if row.get("cadence") and not (row.get("cadence") != row.get("cadence")) else None,
                    feo2=row.get("feo2"),
                    feco2=row.get("feco2"),
                    feto2=row.get("feto2"),
                    fetco2=row.get("fetco2"),
                    ve_vo2=row.get("ve_vo2"),
                    ve_vco2=row.get("ve_vco2"),
                    rer=row.get("rer"),
                    fat_oxidation=row.get("fat_oxidation"),
                    cho_oxidation=row.get("cho_oxidation"),
                    vo2_rel=row.get("vo2_rel"),
                    mets=row.get("mets"),
                    ee_total=row.get("ee_total_calc"),
                    phase=row.get("phase"),
                    data_source=parsed_data.protocol_type,
                    is_valid=True,
                )
                self.db.add(breath)

            await self.db.commit()
            await self.db.refresh(test)

            return test, parsed_data.parsing_errors, parsed_data.parsing_warnings

        finally:
            os.unlink(tmp_path)

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
        phases_query = select(
            BreathData.phase,
            func.min(BreathData.t_sec).label("start_sec"),
            func.max(BreathData.t_sec).label("end_sec"),
            func.count().label("count"),
        ).where(
            and_(
                BreathData.test_id == test_id,
                BreathData.phase.isnot(None),
            )
        ).group_by(BreathData.phase)

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
        if duration_row and duration_row.start is not None and duration_row.end is not None:
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
