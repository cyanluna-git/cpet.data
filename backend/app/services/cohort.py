"""Cohort Analysis Service - 코호트 분석 비즈니스 로직"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
import statistics

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subject, CPETTest, CohortStats
from app.schemas.cohort import (
    CohortFilter,
    MetricStats,
    DistributionBin,
)


class CohortService:
    """코호트 분석 서비스"""

    # 지원하는 메트릭 목록
    VALID_METRICS = [
        "vo2_max",
        "vo2_max_rel",
        "vco2_max",
        "hr_max",
        "fat_max_hr",
        "fat_max_watt",
        "fat_max_g_min",
        "vt1_hr",
        "vt1_vo2",
        "vt2_hr",
        "vt2_vo2",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_filtered_subject_ids(
        self, filters: CohortFilter
    ) -> List[UUID]:
        """필터에 맞는 피험자 ID 목록 조회"""
        current_year = datetime.now().year
        query = select(Subject.id)

        if filters.gender and filters.gender != "All":
            query = query.where(Subject.gender == filters.gender)

        if filters.age_min is not None:
            max_birth_year = current_year - filters.age_min
            query = query.where(Subject.birth_year <= max_birth_year)

        if filters.age_max is not None:
            min_birth_year = current_year - filters.age_max
            query = query.where(Subject.birth_year >= min_birth_year)

        if filters.training_level and filters.training_level != "All":
            query = query.where(Subject.training_level == filters.training_level)

        if filters.job_category:
            query = query.where(Subject.job_category == filters.job_category)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_summary(
        self,
        filters: CohortFilter,
        metrics: List[str],
    ) -> Dict[str, Any]:
        """코호트 요약 통계 조회"""
        # 필터된 피험자 조회
        subject_ids = await self.get_filtered_subject_ids(filters)

        if not subject_ids:
            return {
                "filters_applied": filters,
                "total_subjects": 0,
                "total_tests": 0,
                "metrics": [],
                "last_updated": datetime.utcnow(),
            }

        # 테스트 수 조회
        test_count_result = await self.db.execute(
            select(func.count())
            .select_from(CPETTest)
            .where(CPETTest.subject_id.in_(subject_ids))
        )
        total_tests = test_count_result.scalar() or 0

        # 각 메트릭별 통계 계산
        metric_stats = []
        for metric_name in metrics:
            if metric_name not in self.VALID_METRICS:
                continue

            stats = await self._calculate_metric_stats(subject_ids, metric_name)
            metric_stats.append(stats)

        return {
            "filters_applied": filters,
            "total_subjects": len(subject_ids),
            "total_tests": total_tests,
            "metrics": metric_stats,
            "last_updated": datetime.utcnow(),
        }

    async def _calculate_metric_stats(
        self, subject_ids: List[UUID], metric_name: str
    ) -> MetricStats:
        """특정 메트릭의 통계 계산"""
        # 각 피험자의 최신 테스트에서 해당 메트릭 조회
        metric_col = getattr(CPETTest, metric_name, None)
        if metric_col is None:
            return MetricStats(metric_name=metric_name, sample_size=0)

        # 서브쿼리: 각 피험자의 최신 테스트
        latest_test_subq = (
            select(
                CPETTest.subject_id,
                func.max(CPETTest.test_date).label("max_date"),
            )
            .where(CPETTest.subject_id.in_(subject_ids))
            .group_by(CPETTest.subject_id)
            .subquery()
        )

        # 메인 쿼리: 최신 테스트들의 메트릭 값
        query = (
            select(metric_col)
            .join(
                latest_test_subq,
                and_(
                    CPETTest.subject_id == latest_test_subq.c.subject_id,
                    CPETTest.test_date == latest_test_subq.c.max_date,
                ),
            )
            .where(metric_col.isnot(None))
        )

        result = await self.db.execute(query)
        values = [row[0] for row in result.all() if row[0] is not None]

        if not values:
            return MetricStats(metric_name=metric_name, sample_size=0)

        # 통계 계산
        sorted_values = sorted(values)
        n = len(sorted_values)

        return MetricStats(
            metric_name=metric_name,
            mean=statistics.mean(values),
            median=statistics.median(values),
            std_dev=statistics.stdev(values) if n > 1 else 0,
            min_value=min(values),
            max_value=max(values),
            percentile_10=self._percentile(sorted_values, 10),
            percentile_25=self._percentile(sorted_values, 25),
            percentile_75=self._percentile(sorted_values, 75),
            percentile_90=self._percentile(sorted_values, 90),
            sample_size=n,
        )

    def _percentile(self, sorted_values: List[float], p: int) -> float:
        """백분위 계산"""
        if not sorted_values:
            return 0
        n = len(sorted_values)
        k = (p / 100) * (n - 1)
        f = int(k)
        c = k - f
        if f + 1 < n:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
        return sorted_values[f]

    async def get_distribution(
        self,
        metric: str,
        filters: CohortFilter,
        bins: int = 20,
    ) -> Dict[str, Any]:
        """메트릭 분포 조회"""
        if metric not in self.VALID_METRICS:
            raise ValueError(f"Invalid metric: {metric}")

        subject_ids = await self.get_filtered_subject_ids(filters)

        if not subject_ids:
            return {
                "metric": metric,
                "filters_applied": filters,
                "total_count": 0,
                "bins": [],
            }

        # 메트릭 값 조회
        metric_col = getattr(CPETTest, metric)
        latest_test_subq = (
            select(
                CPETTest.subject_id,
                func.max(CPETTest.test_date).label("max_date"),
            )
            .where(CPETTest.subject_id.in_(subject_ids))
            .group_by(CPETTest.subject_id)
            .subquery()
        )

        query = (
            select(metric_col)
            .join(
                latest_test_subq,
                and_(
                    CPETTest.subject_id == latest_test_subq.c.subject_id,
                    CPETTest.test_date == latest_test_subq.c.max_date,
                ),
            )
            .where(metric_col.isnot(None))
        )

        result = await self.db.execute(query)
        values = [row[0] for row in result.all() if row[0] is not None]

        if not values:
            return {
                "metric": metric,
                "filters_applied": filters,
                "total_count": 0,
                "bins": [],
            }

        # 히스토그램 빈 계산
        min_val = min(values)
        max_val = max(values)
        bin_width = (max_val - min_val) / bins

        # 빈 초기화
        histogram: List[DistributionBin] = []
        for i in range(bins):
            bin_start = min_val + i * bin_width
            bin_end = min_val + (i + 1) * bin_width
            histogram.append(
                DistributionBin(
                    bin_start=bin_start,
                    bin_end=bin_end,
                    count=0,
                    percentage=0,
                )
            )

        # 값들을 빈에 할당
        total = len(values)
        for val in values:
            bin_idx = min(int((val - min_val) / bin_width), bins - 1)
            histogram[bin_idx].count += 1

        # 백분율 계산
        for bin_data in histogram:
            bin_data.percentage = (bin_data.count / total) * 100

        return {
            "metric": metric,
            "filters_applied": filters,
            "total_count": total,
            "bins": histogram,
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
        }

    async def get_percentile(
        self,
        metric: str,
        value: float,
        filters: CohortFilter,
    ) -> Dict[str, Any]:
        """특정 값의 백분위 계산"""
        if metric not in self.VALID_METRICS:
            raise ValueError(f"Invalid metric: {metric}")

        subject_ids = await self.get_filtered_subject_ids(filters)

        if not subject_ids:
            return {
                "metric": metric,
                "value": value,
                "percentile": 0,
                "filters_applied": filters,
                "total_count": 0,
            }

        # 메트릭 값 조회
        metric_col = getattr(CPETTest, metric)
        latest_test_subq = (
            select(
                CPETTest.subject_id,
                func.max(CPETTest.test_date).label("max_date"),
            )
            .where(CPETTest.subject_id.in_(subject_ids))
            .group_by(CPETTest.subject_id)
            .subquery()
        )

        query = (
            select(metric_col)
            .join(
                latest_test_subq,
                and_(
                    CPETTest.subject_id == latest_test_subq.c.subject_id,
                    CPETTest.test_date == latest_test_subq.c.max_date,
                ),
            )
            .where(metric_col.isnot(None))
        )

        result = await self.db.execute(query)
        values = [row[0] for row in result.all() if row[0] is not None]

        if not values:
            return {
                "metric": metric,
                "value": value,
                "percentile": 0,
                "filters_applied": filters,
                "total_count": 0,
            }

        # 백분위 계산
        below_count = sum(1 for v in values if v < value)
        percentile = (below_count / len(values)) * 100

        return {
            "metric": metric,
            "value": value,
            "percentile": percentile,
            "filters_applied": filters,
            "total_count": len(values),
        }

    async def compare_subject(
        self,
        subject_id: UUID,
        test_id: Optional[UUID],
        metrics: List[str],
        filters: CohortFilter,
    ) -> Dict[str, Any]:
        """피험자를 코호트와 비교"""
        # 피험자의 테스트 조회
        if test_id:
            test_query = select(CPETTest).where(CPETTest.test_id == test_id)
        else:
            test_query = (
                select(CPETTest)
                .where(CPETTest.subject_id == subject_id)
                .order_by(CPETTest.test_date.desc())
                .limit(1)
            )

        test_result = await self.db.execute(test_query)
        test = test_result.scalar_one_or_none()

        if not test:
            raise ValueError("Test not found")

        # 코호트 통계 조회
        summary = await self.get_summary(filters, metrics)

        # 비교 결과 생성
        comparisons = []
        for metric_stat in summary["metrics"]:
            metric_name = metric_stat.metric_name
            subject_value = getattr(test, metric_name, None)

            if subject_value is None or metric_stat.sample_size == 0:
                comparisons.append({
                    "metric_name": metric_name,
                    "subject_value": None,
                    "cohort_mean": metric_stat.mean,
                    "cohort_median": metric_stat.median,
                    "percentile": None,
                    "rating": None,
                })
                continue

            # 백분위 계산
            percentile_result = await self.get_percentile(
                metric_name, subject_value, filters
            )
            percentile = percentile_result["percentile"]

            # 등급 부여
            if percentile >= 90:
                rating = "Excellent"
            elif percentile >= 75:
                rating = "Above Average"
            elif percentile >= 25:
                rating = "Average"
            else:
                rating = "Below Average"

            comparisons.append({
                "metric_name": metric_name,
                "subject_value": subject_value,
                "cohort_mean": metric_stat.mean,
                "cohort_median": metric_stat.median,
                "percentile": percentile,
                "rating": rating,
            })

        return {
            "subject_id": test.subject_id,
            "test_id": test.test_id,
            "test_date": test.test_date,
            "filters_applied": filters,
            "cohort_size": summary["total_subjects"],
            "comparisons": comparisons,
        }

    async def save_cohort_stats(
        self,
        gender: Optional[str],
        age_group: Optional[str],
        training_level: Optional[str],
        metrics: Dict[str, MetricStats],
    ) -> None:
        """코호트 통계 저장 (캐싱용)"""
        for metric_name, stats in metrics.items():
            existing = await self.db.execute(
                select(CohortStats).where(
                    and_(
                        CohortStats.gender == gender,
                        CohortStats.age_group == age_group,
                        CohortStats.training_level == training_level,
                        CohortStats.metric_name == metric_name,
                    )
                )
            )
            cohort_stat = existing.scalar_one_or_none()

            if cohort_stat:
                cohort_stat.mean_value = stats.mean
                cohort_stat.median_value = stats.median
                cohort_stat.std_dev = stats.std_dev
                cohort_stat.percentile_10 = stats.percentile_10
                cohort_stat.percentile_25 = stats.percentile_25
                cohort_stat.percentile_75 = stats.percentile_75
                cohort_stat.percentile_90 = stats.percentile_90
                cohort_stat.sample_size = stats.sample_size
                cohort_stat.last_updated = datetime.utcnow()
            else:
                cohort_stat = CohortStats(
                    gender=gender,
                    age_group=age_group,
                    training_level=training_level,
                    metric_name=metric_name,
                    mean_value=stats.mean,
                    median_value=stats.median,
                    std_dev=stats.std_dev,
                    percentile_10=stats.percentile_10,
                    percentile_25=stats.percentile_25,
                    percentile_75=stats.percentile_75,
                    percentile_90=stats.percentile_90,
                    sample_size=stats.sample_size,
                )
                self.db.add(cohort_stat)

        await self.db.commit()

    async def get_comparison(
        self,
        subject_id: UUID,
        test_id: Optional[UUID],
        metrics: List[str],
        filters: CohortFilter,
    ) -> Dict[str, Any]:
        """피험자를 코호트와 비교 (alias for compare_subject)"""
        return await self.compare_subject(subject_id, test_id, metrics, filters)

    async def get_overall_stats(self) -> Dict[str, Any]:
        """전체 데이터베이스 통계 조회"""
        # 총 피험자 수
        subject_count_result = await self.db.execute(
            select(func.count()).select_from(Subject)
        )
        total_subjects = subject_count_result.scalar() or 0

        # 총 테스트 수
        test_count_result = await self.db.execute(
            select(func.count()).select_from(CPETTest)
        )
        total_tests = test_count_result.scalar() or 0

        # 성별 분포
        gender_dist_result = await self.db.execute(
            select(Subject.gender, func.count())
            .group_by(Subject.gender)
        )
        gender_distribution = {
            row[0] or "Unknown": row[1] for row in gender_dist_result.all()
        }

        # 훈련 수준 분포
        training_dist_result = await self.db.execute(
            select(Subject.training_level, func.count())
            .group_by(Subject.training_level)
        )
        training_distribution = {
            row[0] or "Unknown": row[1] for row in training_dist_result.all()
        }

        # 최근 테스트 날짜
        latest_test_result = await self.db.execute(
            select(func.max(CPETTest.test_date))
        )
        latest_test_date = latest_test_result.scalar()

        return {
            "total_subjects": total_subjects,
            "total_tests": total_tests,
            "gender_distribution": gender_distribution,
            "training_distribution": training_distribution,
            "latest_test_date": latest_test_date,
            "last_updated": datetime.utcnow(),
        }
