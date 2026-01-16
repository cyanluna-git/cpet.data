"""JSON Sanitization utilities - NaN/Inf 값 처리"""

import math
from typing import Any, Dict, List, Union


def sanitize_for_json(data: Any, replace_nan_with: Any = None, replace_inf_with: Any = None) -> Any:
    """
    NaN, Inf 값을 JSON 호환 가능한 값으로 변환
    
    Args:
        data: 변환할 데이터 (dict, list, float, 또는 기타)
        replace_nan_with: NaN을 대체할 값 (기본: None)
        replace_inf_with: Inf를 대체할 값 (기본: None)
    
    Returns:
        JSON 직렬화 가능한 데이터
    """
    if isinstance(data, dict):
        return {k: sanitize_for_json(v, replace_nan_with, replace_inf_with) for k, v in data.items()}
    
    elif isinstance(data, list):
        return [sanitize_for_json(item, replace_nan_with, replace_inf_with) for item in data]
    
    elif isinstance(data, tuple):
        return tuple(sanitize_for_json(item, replace_nan_with, replace_inf_with) for item in data)
    
    elif isinstance(data, float):
        if math.isnan(data):
            return replace_nan_with
        elif math.isinf(data):
            return replace_inf_with
        else:
            return data
    
    else:
        return data


def sanitize_breath_data_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    BreathData 행의 NaN/Inf 값을 None으로 변환
    
    Args:
        row_dict: BreathData의 딕셔너리 표현
    
    Returns:
        정제된 딕셔너리
    """
    return sanitize_for_json(row_dict, replace_nan_with=None, replace_inf_with=None)
