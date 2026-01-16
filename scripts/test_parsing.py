"""파싱 로직 직접 테스트"""
import sys
sys.path.insert(0, '/Users/cyanluna-pro16/dev/cpet.db/backend')

from app.services.cosmed_parser import COSMEDParser

file_path = '/Users/cyanluna-pro16/dev/cpet.db/CPET_data/Cho Kwangho 20240718 CPET MIX_20240718094328.xlsx'

try:
    parser = COSMEDParser()
    print("1. Parsing file...")
    parsed_data = parser.parse_file(file_path)
    print(f"   ✓ Parsed: {len(parsed_data.time_series)} rows")
    print(f"   Test date: {parsed_data.test.test_date}")
    
    print("2. Calculating metrics...")
    df = parser.calculate_metabolic_metrics(parsed_data, calc_method="Frayn", smoothing_window=10)
    print(f"   ✓ DataFrame shape: {df.shape}")
    
    print("3. Detecting phases...")
    df = parser.detect_phases(df)
    print(f"   ✓ Phases: {df['phase'].value_counts().to_dict()}")
    
    print("4. Getting phase boundaries...")
    boundaries = parser.get_phase_boundaries(df)
    print(f"   ✓ Boundaries: {boundaries}")
    
    print("5. Calculating phase metrics...")
    metrics = parser.calculate_phase_metrics(df)
    print(f"   ✓ Metrics keys: {list(metrics.keys()) if metrics else 'None'}")
    
    print("6. Finding VO2MAX...")
    vo2max = parser.find_vo2max(df)
    print(f"   ✓ VO2MAX: {vo2max}")
    
    print("7. Finding FATMAX...")
    fatmax = parser.find_fatmax(df)
    print(f"   ✓ FATMAX: {fatmax}")
    
    print("8. Detecting VT thresholds...")
    vt = parser.detect_ventilatory_thresholds(df, method='v_slope')
    print(f"   ✓ VT: {vt}")
    
    print("\n✅ All parsing steps completed successfully!")
    
except Exception as e:
    import traceback
    print(f"\n❌ Error: {e}")
    traceback.print_exc()
