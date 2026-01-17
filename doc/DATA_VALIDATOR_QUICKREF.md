# DataValidator Quick Reference

## Import

```python
from app.services.data_validator import DataValidator
from app.schemas.test import ValidationResult, ProtocolType
```

## Basic Usage

```python
# Initialize validator
validator = DataValidator()

# Validate DataFrame
result = validator.validate(df)

# Check result
if result.is_valid:
    print(f"✓ Valid {result.protocol_type.value} test")
    print(f"Quality: {result.quality_score:.2f}")
else:
    print(f"✗ Invalid: {', '.join(result.reason)}")
```

## Validation Criteria

| Check | Requirement | Action if Failed |
|-------|-------------|------------------|
| Essential columns | t, bike_power, hr, vo2, vco2 | Reject |
| Duration | Exercise ≥ 300s (5min) | Reject |
| Max Power | ≥ 50W | Reject |
| HR Dropout | < 10% | Reject |
| Gas Dropout | VO2/VCO2 < 10% | Reject |

## Protocol Classification

```python
if result.protocol_type == ProtocolType.RAMP:
    # r >= 0.85: Linear power increase
    # → Run FatMax/VT analysis
    pass
elif result.protocol_type == ProtocolType.INTERVAL:
    # r < 0.85, high variation
    # → Save data only, skip analysis
    pass
elif result.protocol_type == ProtocolType.STEADY_STATE:
    # r < 0.85, low variation
    # → Save data only, skip analysis
    pass
```

## Quality Score

```
1.00 = Perfect data
0.90 = Minor sensor dropouts (< 5%)
0.70 = Major sensor dropouts (10-15%)
0.50 = Missing essential columns
0.00 = Unusable data
```

## Validation Result Fields

```python
result.is_valid                  # bool: Can use data?
result.protocol_type             # ProtocolType enum
result.reason                    # List[str]: Failure reasons
result.quality_score             # float: 0.0-1.0
result.metadata                  # Dict: Detailed metrics
result.has_essential_columns     # bool
result.duration_valid            # bool
result.intensity_valid           # bool
result.hr_integrity              # bool
result.gas_integrity             # bool
result.power_time_correlation    # float: Pearson r
```

## Metadata Fields

```python
result.metadata["duration_sec"]        # Exercise duration (seconds)
result.metadata["duration_min"]        # Exercise duration (minutes)
result.metadata["max_power"]           # Max power (Watts)
result.metadata["hr_dropout_rate"]     # 0.0-1.0
result.metadata["vo2_dropout_rate"]    # 0.0-1.0
result.metadata["vco2_dropout_rate"]   # 0.0-1.0
result.metadata["total_data_points"]   # Total rows
result.metadata["exercise_data_points"]# Exercise phase rows
result.metadata["power_time_correlation"] # Pearson r
result.metadata["quality_score"]       # Same as result.quality_score
```

## Print Summary

```python
print(validator.get_validation_summary(result))
```

Output:
```
============================================================
CPET Data Validation Report
============================================================
Valid: ✓ YES
Protocol: RAMP
Quality Score: 1.00/1.00

Details:
  Essential Columns: ✓
  Duration: ✓ (15.00 min)
  Intensity: ✓ (Max Power: 300.0W)
  HR Sensor: ✓ (Dropout: 0.0%)
  Gas Sensor: ✓ (VO2: 0.0%, VCO2: 0.0%)
  Power-Time Correlation: r=0.987
============================================================
```

## Configuration

Adjust thresholds in `DataValidator`:

```python
class DataValidator:
    MIN_EXERCISE_DURATION_SEC = 300   # 5 minutes
    MIN_MAX_POWER = 50                # Watts
    MAX_DROPOUT_RATE = 0.10           # 10%
    EXERCISE_POWER_THRESHOLD = 20     # Watts
    RAMP_CORRELATION_THRESHOLD = 0.85 # Pearson r
```

## Common Patterns

### Pattern 1: Validate Before Analysis

```python
validator = DataValidator()
result = validator.validate(df)

if not result.is_valid:
    raise ValueError(f"Invalid data: {', '.join(result.reason)}")

if result.protocol_type != ProtocolType.RAMP:
    raise ValueError(f"Only RAMP protocols supported, got {result.protocol_type}")

# Proceed with analysis
analyzer = MetabolismAnalyzer()
fatmax_result = analyzer.analyze_fatmax(df)
```

### Pattern 2: Conditional Analysis

```python
result = validator.validate(df)

if result.is_valid:
    if result.protocol_type == ProtocolType.RAMP:
        # Full analysis
        fatmax = analyzer.analyze_fatmax(df)
        vt = analyzer.detect_vt(df)
    else:
        # Save data only
        save_raw_data(df)
else:
    # Reject upload
    raise ValidationError(result.reason)
```

### Pattern 3: Quality-Based Warning

```python
result = validator.validate(df)

if result.quality_score < 0.8:
    warnings.append(f"⚠️ Data quality low ({result.quality_score:.2f})")
    warnings.append(f"Issues: {', '.join(result.reason)}")

if result.quality_score >= 0.95:
    print("✓ Excellent data quality")
```

## Testing

Run test suite:

```bash
python tests/test_data_validator.py
```

Scenarios:
- ✓ Valid RAMP test
- ✓ Interval training
- ✓ Steady-state test
- ✗ Short duration (< 5min)
- ✗ Low intensity (< 50W)
- ✗ HR dropout (> 10%)
- ✗ Gas dropout (> 10%)
- ✗ Missing columns

## Error Handling

```python
try:
    result = validator.validate(df)
except Exception as e:
    # Unexpected error (e.g., malformed DataFrame)
    print(f"Validation error: {e}")
    result = ValidationResult(
        is_valid=False,
        protocol_type=ProtocolType.UNKNOWN,
        reason=[str(e)],
        quality_score=0.0
    )
```

## Integration with TestService

Automatically integrated in `TestService.upload_and_parse()`:

```python
# Upload file → Automatic validation
test, errors, warnings = await test_service.upload_and_parse(
    file_content=file.read(),
    filename=file.filename,
    subject_id=subject_id
)

# Check status
if test.parsing_status == "validation_failed":
    # Invalid data
    print(f"Validation failed: {test.parsing_errors}")
elif test.parsing_status == "skipped_protocol_mismatch":
    # Valid data, wrong protocol
    print(f"Protocol mismatch: {test.protocol_type}")
else:
    # Success
    print(f"Analysis complete: FatMax={test.fat_max_watt}W")
```

## Best Practices

1. **Always validate before analysis**
   - Prevents garbage-in-garbage-out
   - Saves computation time

2. **Check protocol_type before running algorithms**
   - FatMax/VT detection requires RAMP
   - Other protocols need different approaches

3. **Use quality_score for warnings**
   - < 0.8: Show warning to user
   - < 0.5: Recommend re-testing

4. **Store validation_result.metadata**
   - Helps debugging upload issues
   - Useful for quality reports

5. **Handle edge cases gracefully**
   - Empty DataFrames
   - Single-row data
   - Missing columns
