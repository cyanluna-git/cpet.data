"""Test DataValidator Service - 데이터 검증 및 프로토콜 분류 테스트"""

import asyncio
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.data_validator import DataValidator
from app.schemas.test import ProtocolType


def create_test_data(scenario: str) -> pd.DataFrame:
    """테스트 데이터 생성
    
    Scenarios:
    - ramp_valid: 정상적인 Ramp 프로토콜
    - interval: 인터벌 트레이닝
    - steady_state: 정상 상태 테스트
    - short_duration: 짧은 테스트 (< 5분)
    - low_intensity: 낮은 강도 (< 50W)
    - hr_dropout: HR 센서 드롭아웃
    - gas_dropout: Gas 센서 드롭아웃
    - missing_columns: 필수 컬럼 누락
    """
    
    if scenario == "ramp_valid":
        # 정상 Ramp 테스트: 0W → 300W, 15분
        n_points = 180  # 5초 간격, 15분
        t_sec = np.linspace(0, 900, n_points)
        power = np.linspace(0, 300, n_points)
        hr = 60 + (power * 0.5) + np.random.normal(0, 2, n_points)
        vo2 = 400 + (power * 10) + np.random.normal(0, 50, n_points)
        vco2 = 350 + (power * 9) + np.random.normal(0, 45, n_points)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "interval":
        # 인터벌 트레이닝: 5분 x 6세트 (2분 easy, 3분 hard)
        n_points = 360  # 5초 간격, 30분
        t_sec = np.linspace(0, 1800, n_points)
        
        # 2분 100W, 3분 250W 반복
        power = []
        for i in range(n_points):
            cycle_time = t_sec[i] % 300  # 5분 사이클
            if cycle_time < 120:  # 0-2분: Easy
                power.append(100 + np.random.normal(0, 5))
            else:  # 2-5분: Hard
                power.append(250 + np.random.normal(0, 10))
        
        power = np.array(power)
        hr = 80 + (power * 0.4) + np.random.normal(0, 3, n_points)
        vo2 = 600 + (power * 8) + np.random.normal(0, 60, n_points)
        vco2 = 550 + (power * 7) + np.random.normal(0, 55, n_points)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "steady_state":
        # 정상 상태: 200W 30분
        n_points = 360  # 5초 간격, 30분
        t_sec = np.linspace(0, 1800, n_points)
        power = 200 + np.random.normal(0, 5, n_points)
        hr = 140 + np.random.normal(0, 2, n_points)
        vo2 = 2500 + np.random.normal(0, 50, n_points)
        vco2 = 2300 + np.random.normal(0, 45, n_points)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "short_duration":
        # 짧은 테스트: 3분만
        n_points = 36
        t_sec = np.linspace(0, 180, n_points)
        power = np.linspace(0, 100, n_points)
        hr = 60 + (power * 0.5)
        vo2 = 400 + (power * 10)
        vco2 = 350 + (power * 9)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "low_intensity":
        # 낮은 강도: 최대 40W
        n_points = 120
        t_sec = np.linspace(0, 600, n_points)
        power = np.linspace(0, 40, n_points)
        hr = 60 + (power * 0.3)
        vo2 = 400 + (power * 5)
        vco2 = 350 + (power * 4)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "hr_dropout":
        # HR 센서 드롭아웃 (15%)
        n_points = 180
        t_sec = np.linspace(0, 900, n_points)
        power = np.linspace(0, 300, n_points)
        hr = 60 + (power * 0.5)
        
        # 15% 드롭아웃
        dropout_indices = np.random.choice(n_points, size=int(n_points * 0.15), replace=False)
        hr[dropout_indices] = 0
        
        vo2 = 400 + (power * 10)
        vco2 = 350 + (power * 9)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "gas_dropout":
        # Gas 센서 드롭아웃 (12%)
        n_points = 180
        t_sec = np.linspace(0, 900, n_points)
        power = np.linspace(0, 300, n_points)
        hr = 60 + (power * 0.5)
        vo2 = 400 + (power * 10)
        vco2 = 350 + (power * 9)
        
        # 12% 드롭아웃
        dropout_indices = np.random.choice(n_points, size=int(n_points * 0.12), replace=False)
        vo2[dropout_indices] = np.nan
        vco2[dropout_indices] = 0
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr,
            'vo2': vo2,
            'vco2': vco2
        })
    
    elif scenario == "missing_columns":
        # 필수 컬럼 누락 (VO2만)
        n_points = 180
        t_sec = np.linspace(0, 900, n_points)
        power = np.linspace(0, 300, n_points)
        hr = 60 + (power * 0.5)
        
        return pd.DataFrame({
            't_sec': t_sec,
            'bike_power': power,
            'hr': hr
        })
    
    else:
        raise ValueError(f"Unknown scenario: {scenario}")


def _run_scenario(scenario: str, expected_valid: bool, expected_protocol: ProtocolType):
    """시나리오 테스트 (내부 헬퍼 함수)"""
    print(f"\n{'='*70}")
    print(f"Testing Scenario: {scenario}")
    print(f"{'='*70}")
    
    # 테스트 데이터 생성
    df = create_test_data(scenario)
    print(f"Generated {len(df)} data points")
    print(f"Columns: {list(df.columns)}")
    
    # 검증 실행
    validator = DataValidator()
    result = validator.validate(df)
    
    # 결과 출력
    print(f"\n{validator.get_validation_summary(result)}")
    
    # Assertion
    assert result.is_valid == expected_valid, \
        f"Expected is_valid={expected_valid}, got {result.is_valid}"
    
    if expected_protocol != ProtocolType.UNKNOWN:
        assert result.protocol_type == expected_protocol, \
            f"Expected protocol={expected_protocol}, got {result.protocol_type}"
    
    print(f"✓ Test PASSED")
    return result


def main():
    """모든 시나리오 테스트"""
    print("="*70)
    print("DataValidator Service - Comprehensive Test Suite")
    print("="*70)
    
    scenarios = [
        # (scenario_name, expected_valid, expected_protocol)
        ("ramp_valid", True, ProtocolType.RAMP),
        ("interval", True, ProtocolType.INTERVAL),
        ("steady_state", True, ProtocolType.STEADY_STATE),
        ("short_duration", False, ProtocolType.RAMP),  # Too short
        ("low_intensity", False, ProtocolType.RAMP),   # Too low
        ("hr_dropout", False, ProtocolType.RAMP),      # HR dropout > 10%
        ("gas_dropout", False, ProtocolType.RAMP),     # Gas dropout > 10%
        ("missing_columns", False, ProtocolType.UNKNOWN),  # Missing VO2/VCO2
    ]
    
    results = []
    passed = 0
    failed = 0
    
    for scenario, expected_valid, expected_protocol in scenarios:
        try:
            result = _run_scenario(scenario, expected_valid, expected_protocol)
            results.append((scenario, "PASS", result))
            passed += 1
        except AssertionError as e:
            print(f"✗ Test FAILED: {e}")
            results.append((scenario, "FAIL", str(e)))
            failed += 1
        except Exception as e:
            print(f"✗ Test ERROR: {e}")
            results.append((scenario, "ERROR", str(e)))
            failed += 1
    
    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    for scenario, status, _ in results:
        symbol = "✓" if status == "PASS" else "✗"
        print(f"{symbol} {scenario:20s} - {status}")
    
    print(f"\nTotal: {len(scenarios)} | Passed: {passed} | Failed: {failed}")
    print("="*70)
    
    if failed == 0:
        print("🎉 All tests PASSED!")
    else:
        print(f"⚠️  {failed} test(s) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
