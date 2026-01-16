"""실패 파일 파싱 테스트"""
import sys
sys.path.insert(0, '/Users/cyanluna-pro16/dev/cpet.db/backend')
from app.services.cosmed_parser import COSMEDParser

file_path = '/Users/cyanluna-pro16/dev/cpet.db/CPET_data/Hong Changsun 20240718 CPET MIX_20240718125243.xlsx'

print('파싱 시작...')
parser = COSMEDParser()

try:
    parsed = parser.parse_file(file_path)
    print(f'✓ 파싱 성공: {len(parsed.time_series)} rows')
    print(f'  Subject: {parsed.subject.first_name} {parsed.subject.last_name}')
    print(f'  Test Date: {parsed.test.test_date}')
    
    df = parser.calculate_metabolic_metrics(parsed, 'Frayn', 10)
    print(f'✓ 메트릭 계산 완료: {df.shape}')
    
    df = parser.detect_phases(df)
    print(f'✓ Phase 감지: {df["phase"].value_counts().to_dict()}')
    
    vo2max = parser.find_vo2max(df)
    print(f'✓ VO2MAX: {vo2max}')
    
    fatmax = parser.find_fatmax(df)
    print(f'✓ FATMAX: {fatmax}')
    
    print()
    print('✅ 파싱 전체 성공! 파일 형식에 문제 없음')
    
except Exception as e:
    import traceback
    print(f'❌ Error: {e}')
    traceback.print_exc()
