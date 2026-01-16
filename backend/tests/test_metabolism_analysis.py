"""Test metabolism analysis pipeline - 대사 분석 파이프라인 테스트"""

import pytest
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.cosmed_parser import COSMEDParser


class TestPhaseDetection:
    """구간 감지 테스트"""

    @pytest.fixture
    def parser(self):
        return COSMEDParser()

    @pytest.fixture
    def sample_file(self):
        """Get first available sample file"""
        data_dir = Path(__file__).parent.parent.parent / "CPET_data"
        xlsx_files = list(data_dir.glob("*.xlsx"))
        if xlsx_files:
            return xlsx_files[0]
        pytest.skip("No sample CPET files found")

    def test_parse_file(self, parser, sample_file):
        """파일 파싱 테스트"""
        parsed = parser.parse_file(sample_file)

        assert parsed is not None
        assert parsed.subject is not None
        assert parsed.time_series is not None
        assert len(parsed.time_series) > 0

        # Check required columns exist
        assert 'vo2' in parsed.time_series.columns
        assert 'vco2' in parsed.time_series.columns

        print(f"\n파싱 결과:")
        print(f"  - 피험자: {parsed.subject.research_id}")
        print(f"  - 프로토콜: {parsed.protocol_type}")
        print(f"  - 데이터 포인트: {len(parsed.time_series)}")

    def test_calculate_metabolic_metrics(self, parser, sample_file):
        """대사 지표 계산 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed, calc_method='Frayn')

        assert 'fat_oxidation' in df.columns
        assert 'cho_oxidation' in df.columns
        assert 'ee_total_calc' in df.columns

        # Check values are reasonable
        assert df['fat_oxidation'].max() <= 2.0  # g/min
        assert df['fat_oxidation'].min() >= 0

        print(f"\n대사 지표:")
        print(f"  - 최대 지방 산화: {df['fat_oxidation'].max():.3f} g/min")
        print(f"  - 최대 탄수화물 산화: {df['cho_oxidation'].max():.3f} g/min")

    def test_detect_phases(self, parser, sample_file):
        """구간 감지 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed)
        df_with_phases = parser.detect_phases(df)

        assert 'phase' in df_with_phases.columns

        # Check phases detected
        phases = df_with_phases['phase'].unique()
        print(f"\n감지된 구간: {list(phases)}")

        # At least some phases should be detected
        assert len(phases) > 0

        # Get phase boundaries
        boundaries = parser.get_phase_boundaries(df_with_phases)
        assert boundaries is not None
        assert 'phases' in boundaries

        print(f"\n구간 경계:")
        for phase_info in boundaries.get('phases', []):
            print(f"  - {phase_info['phase']}: {phase_info['start_sec']:.0f}s ~ {phase_info['end_sec']:.0f}s")

    def test_find_fatmax(self, parser, sample_file):
        """FATMAX 감지 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed)
        fatmax = parser.find_fatmax(df)

        assert fatmax is not None
        assert 'fat_max_g_min' in fatmax

        print(f"\nFATMAX:")
        print(f"  - 최대 지방 산화: {fatmax.get('fat_max_g_min', 'N/A')} g/min")
        print(f"  - HR: {fatmax.get('fat_max_hr', 'N/A')} bpm")
        print(f"  - Power: {fatmax.get('fat_max_watt', 'N/A')} W")

    def test_find_vo2max(self, parser, sample_file):
        """VO2MAX 감지 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed)
        vo2max = parser.find_vo2max(df)

        assert vo2max is not None
        assert 'vo2_max' in vo2max

        print(f"\nVO2MAX:")
        print(f"  - VO2max: {vo2max.get('vo2_max', 'N/A')} ml/min")
        print(f"  - VO2max/kg: {vo2max.get('vo2_max_rel', 'N/A')} ml/kg/min")
        print(f"  - HRmax: {vo2max.get('hr_max', 'N/A')} bpm")

    def test_detect_vt_thresholds(self, parser, sample_file):
        """VT 역치 감지 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed)
        df_with_phases = parser.detect_phases(df)

        vt = parser.detect_ventilatory_thresholds(df_with_phases, method='v_slope')

        print(f"\n환기 역치:")
        print(f"  - VT1: HR {vt.get('vt1_hr', 'N/A')} bpm, VO2 {vt.get('vt1_vo2', 'N/A')} ml/min")
        print(f"  - VT2: HR {vt.get('vt2_hr', 'N/A')} bpm, VO2 {vt.get('vt2_vo2', 'N/A')} ml/min")
        print(f"  - 감지 방법: {vt.get('detection_method', 'N/A')}")
        print(f"  - 신뢰도: {vt.get('confidence', 0) * 100:.0f}%")

    def test_phase_metrics(self, parser, sample_file):
        """구간별 메트릭 계산 테스트"""
        parsed = parser.parse_file(sample_file)
        df = parser.calculate_metabolic_metrics(parsed)
        df_with_phases = parser.detect_phases(df)
        phase_metrics = parser.calculate_phase_metrics(df_with_phases)

        assert phase_metrics is not None

        print(f"\n구간별 메트릭:")
        for phase, metrics in phase_metrics.items():
            print(f"\n  [{phase}]")
            print(f"    - 시간: {metrics.get('duration_sec', 0):.0f}s")
            print(f"    - 평균 HR: {metrics.get('avg_hr', 'N/A')}")
            print(f"    - 평균 VO2: {metrics.get('avg_vo2', 'N/A')}")
            print(f"    - 평균 RER: {metrics.get('avg_rer', 'N/A')}")
            print(f"    - 평균 지방 산화: {metrics.get('avg_fat_oxidation', 'N/A')}")


class TestFullPipeline:
    """전체 파이프라인 테스트"""

    def test_full_analysis_pipeline(self):
        """전체 분석 파이프라인 테스트"""
        # Find sample file
        data_dir = Path(__file__).parent.parent.parent / "CPET_data"
        xlsx_files = list(data_dir.glob("*.xlsx"))

        if not xlsx_files:
            pytest.skip("No sample CPET files found")

        sample_file = xlsx_files[0]
        print(f"\n테스트 파일: {sample_file.name}")

        parser = COSMEDParser()

        # 1. Parse file
        parsed = parser.parse_file(sample_file)
        assert parsed is not None

        # 2. Calculate metabolic metrics
        df = parser.calculate_metabolic_metrics(parsed, calc_method='Frayn')
        assert 'fat_oxidation' in df.columns

        # 3. Detect phases
        df_with_phases = parser.detect_phases(df)
        assert 'phase' in df_with_phases.columns

        # 4. Get phase boundaries
        boundaries = parser.get_phase_boundaries(df_with_phases)
        assert 'phases' in boundaries

        # 5. Calculate phase metrics
        phase_metrics = parser.calculate_phase_metrics(df_with_phases)
        assert len(phase_metrics) > 0

        # 6. Find FATMAX
        fatmax = parser.find_fatmax(df_with_phases)
        assert 'fat_max_g_min' in fatmax

        # 7. Find VO2MAX
        vo2max = parser.find_vo2max(df_with_phases)
        assert 'vo2_max' in vo2max

        # 8. Detect VT thresholds
        vt = parser.detect_ventilatory_thresholds(df_with_phases)

        print("\n✅ 전체 파이프라인 테스트 통과!")
        print("\n=== 분석 결과 요약 ===")
        print(f"피험자: {parsed.subject.research_id}")
        print(f"프로토콜: {parsed.protocol_type}")
        print(f"데이터 포인트: {len(df_with_phases)}")
        print(f"감지된 구간: {df_with_phases['phase'].unique().tolist()}")
        print(f"FATMAX: {fatmax.get('fat_max_g_min', 'N/A'):.3f} g/min @ {fatmax.get('fat_max_watt', 'N/A')} W")
        print(f"VO2MAX: {vo2max.get('vo2_max', 'N/A'):.0f} ml/min")
        print(f"HRmax: {vo2max.get('hr_max', 'N/A')} bpm")
        if vt.get('vt1_hr'):
            print(f"VT1: HR {vt['vt1_hr']} bpm")
        if vt.get('vt2_hr'):
            print(f"VT2: HR {vt['vt2_hr']} bpm")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
