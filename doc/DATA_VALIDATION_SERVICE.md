# CPET Data Validation & Protocol Classification Service

## Overview

The **DataValidator** service is a critical gatekeeper that runs immediately after parsing CPET Excel files. It validates data integrity and classifies the test protocol to ensure only suitable data proceeds to analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     File Upload Flow                             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ COSMEDParser │  Parse Excel → DataFrame
                    └──────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │DataValidator │  Validation + Classification
                    └──────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
         [INVALID DATA]          [VALID DATA]
                │                       │
                ▼               ┌───────┴────────┐
        Save w/ Error      RAMP │    INTERVAL   │ STEADY_STATE
         Skip Analysis           │               │
                                 ▼               ▼
                        Standard Analysis    Save Data Only
                        (FatMax, VT, etc)    (No Analysis)
```

## Features

### 1. Data Integrity Validation

The validator checks 5 essential criteria:

| Criterion | Check | Threshold | Failure Action |
|-----------|-------|-----------|----------------|
| **Essential Columns** | Must have: `t`, `bike_power`, `hr`, `vo2`, `vco2` | N/A | Reject |
| **Duration** | Exercise phase (Power > 20W) duration | ≥ 300s (5 min) | Reject |
| **Intensity** | Maximum power during exercise | ≥ 50W | Reject |
| **HR Sensor** | HR dropout rate (NaN or 0) | < 10% | Reject |
| **Gas Sensor** | VO2/VCO2 dropout rate | < 10% | Reject |

### 2. Protocol Classification

Uses **Pearson Correlation Coefficient** ($r$) between Time and Power:

```python
r = pearson(Time, Power)  # During exercise phase
```

| Protocol Type | Correlation | Power Pattern | Analysis Support |
|---------------|-------------|---------------|------------------|
| **RAMP** | $r \geq 0.85$ | Linear increase | ✓ Full (FatMax, VT) |
| **INTERVAL** | $r < 0.85$, CV > 30% | Fluctuating | ✗ Data saved only |
| **STEADY_STATE** | $r < 0.85$, CV ≤ 30% | Constant | ✗ Data saved only |
| **UNKNOWN** | N/A | Unclassifiable | ✗ Rejected |

### 3. Quality Score Calculation

Weighted scoring (0.0 - 1.0):

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Essential Columns | 20% | Pass: 0.20, Fail: 0.00 |
| Duration | 15% | Pass: 0.15, Fail: 0.00 |
| Intensity | 15% | Pass: 0.15, Fail: 0.00 |
| HR Integrity | 20% | `0.20 × (1 - dropout_rate / 0.10)` |
| Gas Integrity | 30% | `0.15 × VO2_quality + 0.15 × VCO2_quality` |

**Example:**
```
Ramp Test (Perfect): 1.00
HR Dropout 5%: 0.90 (partial credit)
Gas Dropout 12%: 0.70 (failed gas sensor)
```

## Implementation

### ValidationResult Schema

```python
class ProtocolType(str, Enum):
    RAMP = "RAMP"
    INTERVAL = "INTERVAL"
    STEADY_STATE = "STEADY_STATE"
    UNKNOWN = "UNKNOWN"

class ValidationResult(BaseModel):
    is_valid: bool                        # Can we use this data?
    protocol_type: ProtocolType           # Classified protocol
    reason: List[str]                     # Failure reasons
    quality_score: float                  # 0.0 - 1.0
    metadata: Dict[str, Any]              # Detailed metrics
    
    # Detailed checks
    has_essential_columns: bool
    duration_valid: bool
    intensity_valid: bool
    hr_integrity: bool
    gas_integrity: bool
    power_time_correlation: Optional[float]  # r value
```

### DataValidator Service

```python
from app.services.data_validator import DataValidator

validator = DataValidator()
result = validator.validate(df)

if result.is_valid:
    if result.protocol_type == ProtocolType.RAMP:
        # Proceed with standard analysis
        pass
    else:
        # Save data only, skip analysis
        pass
else:
    # Reject upload or save with error status
    pass
```

## Integration with TestService

Modified `upload_and_parse()` workflow:

```python
async def upload_and_parse(self, file_content, filename, subject_id):
    # 1. Parse Excel file
    parser = COSMEDParser()
    parsed_data = parser.parse_file(tmp_path)
    
    # 2. VALIDATE DATA
    validator = DataValidator()
    validation_result = validator.validate(parsed_data.breath_data_df)
    
    # 3. BRANCHING LOGIC
    if not validation_result.is_valid:
        # Save with error status, skip analysis
        test = CPETTest(
            parsing_status="validation_failed",
            data_quality_score=validation_result.quality_score,
            parsing_errors={"validation_errors": validation_result.reason}
        )
        return test, validation_result.reason, ["Data validation failed"]
    
    if validation_result.protocol_type != ProtocolType.RAMP:
        # Save data only, skip analysis
        test = CPETTest(
            parsing_status="skipped_protocol_mismatch",
            data_quality_score=validation_result.quality_score
        )
        # Save BreathData but no analysis
        return test, [], ["Protocol mismatch - analysis skipped"]
    
    # 4. PROCEED WITH STANDARD ANALYSIS (RAMP only)
    df_with_metrics = parser.calculate_metabolic_metrics(...)
    fatmax_metrics = parser.find_fatmax(...)
    # ... continue with FatMax, VT detection
```

## Test Results

Comprehensive test suite with 8 scenarios:

```bash
$ python tests/test_data_validator.py

✓ ramp_valid           - PASS  (r=1.000, Quality=1.00)
✓ interval             - PASS  (r=0.120, Quality=1.00)
✓ steady_state         - PASS  (r=0.009, Quality=1.00)
✓ short_duration       - PASS  (Duration=2.31min < 5min, Quality=0.85)
✓ low_intensity        - PASS  (MaxPower=40W < 50W, Quality=0.70)
✓ hr_dropout           - PASS  (HR Dropout=13.7%, Quality=0.80)
✓ gas_dropout          - PASS  (Gas Dropout=11.9%, Quality=0.70)
✓ missing_columns      - PASS  (Missing VO2/VCO2, Quality=0.50)

Total: 8 | Passed: 8 | Failed: 0
🎉 All tests PASSED!
```

## API Response Examples

### Successful RAMP Test

```json
{
  "test_id": "abc-123",
  "parsing_status": "success",
  "data_quality_score": 1.0,
  "protocol_type": "RAMP",
  "vo2_max": 4500,
  "fat_max_watt": 170,
  "fat_max_g_min": 0.63
}
```

### Invalid Data (Sensor Failure)

```json
{
  "test_id": "abc-456",
  "parsing_status": "validation_failed",
  "data_quality_score": 0.70,
  "protocol_type": "RAMP",
  "parsing_errors": {
    "validation_errors": [
      "Gas sensor dropout rate too high: VO2=12.5%, VCO2=11.8% (> 10%)"
    ],
    "quality_score": 0.70,
    "metadata": {
      "duration_min": 15.2,
      "max_power": 320,
      "vo2_dropout_rate": 0.125,
      "vco2_dropout_rate": 0.118
    }
  }
}
```

### Protocol Mismatch (Interval Training)

```json
{
  "test_id": "abc-789",
  "parsing_status": "skipped_protocol_mismatch",
  "data_quality_score": 1.0,
  "protocol_type": "INTERVAL",
  "parsing_errors": {
    "protocol_type": "INTERVAL",
    "reason": "Protocol type INTERVAL is not suitable for standard analysis (FatMax/VT). Only RAMP protocols are supported.",
    "metadata": {
      "power_time_correlation": 0.12,
      "duration_min": 30.0,
      "max_power": 280
    }
  }
}
```

## Configuration

### Adjustable Thresholds

In `DataValidator` class:

```python
# Change these if needed
MIN_EXERCISE_DURATION_SEC = 300  # 5 minutes
MIN_MAX_POWER = 50               # Watts
MAX_DROPOUT_RATE = 0.10          # 10%
EXERCISE_POWER_THRESHOLD = 20    # Watts (to define exercise phase)
RAMP_CORRELATION_THRESHOLD = 0.85  # Pearson r for RAMP classification
```

### Column Name Handling

Supports alternative column names:

```python
ALTERNATIVE_COLUMNS = {
    't': ['time', 't_sec', 'Time'],
    'bike_power': ['power', 'Power', 'Bike Power', 'watt'],
    'hr': ['HR', 'Heart Rate'],
    'vo2': ['VO2', 'vo2_ml_min'],
    'vco2': ['VCO2', 'vco2_ml_min']
}
```

## Use Cases

### Use Case 1: Lab Technician Uploads File
- **Scenario**: Upload a COSMED K5 file with good data
- **Result**: Validation passes, analysis runs automatically
- **UI**: Shows "✓ Valid RAMP Test | Quality: 1.0"

### Use Case 2: Athlete Uploads Training Ride
- **Scenario**: Upload a .fit file from interval training
- **Result**: Valid data, but protocol = INTERVAL
- **UI**: Shows "⚠️ Interval detected - standard analysis not available"

### Use Case 3: Sensor Malfunction During Test
- **Scenario**: HR strap disconnected for 3 minutes (15% dropout)
- **Result**: Validation fails, data saved but not analyzed
- **UI**: Shows "✗ HR sensor failure (15% dropout) - data quality too low"

### Use Case 4: Incomplete Test
- **Scenario**: Test stopped early (only 3 minutes)
- **Result**: Validation fails (duration < 5min)
- **UI**: Shows "✗ Test too short (3.2 min) - minimum 5 minutes required"

## Future Enhancements

1. **Custom Thresholds per User/Lab**
   - Allow admins to configure thresholds
   - Store in database settings

2. **Advanced Protocol Detection**
   - Machine learning classifier for complex protocols
   - Support for hybrid protocols (Ramp + Steady-state)

3. **Auto-Repair Suggestions**
   - Interpolate missing HR data (if < 5% dropout)
   - Suggest re-running test with specific improvements

4. **Real-time Validation**
   - Validate during test (live feedback to technician)
   - Warning if dropout rate increasing

5. **Protocol-Specific Analysis**
   - Interval training: Power distribution, recovery rates
   - Steady-state: Metabolic efficiency, drift analysis

## Summary

The DataValidator service ensures:
- ✓ Only high-quality data proceeds to analysis
- ✓ Prevents garbage-in-garbage-out scenarios
- ✓ Classifies protocol types automatically
- ✓ Provides clear feedback on rejection reasons
- ✓ Maintains data quality standards across the platform

This is a **critical quality gate** that protects the integrity of all downstream analysis.
