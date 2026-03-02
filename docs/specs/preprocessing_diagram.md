@startuml
skinparam classAttributeIconSize 0
skinparam linetype ortho

package "Data Models" {
    class ProcessedDataPoint {
        + power: float
        + fat_oxidation: float
        + cho_oxidation: float
        + vo2: float
        + vco2: float
        + rer: float
        + count: int
    }

    class FatMaxMarker {
        + power: int
        + mfo: float
        + zone_min: int
        + zone_max: int
    }

    class CrossoverMarker {
        + power: int
        + fat_value: float
        + cho_value: float
    }

    class MetabolicMarkers {
        + fat_max: FatMaxMarker
        + crossover: CrossoverMarker
    }

    class ProcessedSeries {
        + raw: List[ProcessedDataPoint]
        + binned: List[ProcessedDataPoint]
        + smoothed: List[ProcessedDataPoint]
        + trend: List[ProcessedDataPoint]
    }
    
    class MetabolismAnalysisResult {
        + processed_series: ProcessedSeries
        + metabolic_markers: MetabolicMarkers
        + warnings: List[str]
    }
}

package "Configuration" {
    class AnalysisConfig {
        + loess_frac: float
        + bin_size: int
        + aggregation_method: str
        + gas_delay_seconds: float
        + outlier_window_size: int
        + trend_gap_threshold_watts: int
        .. flags ..
        + exclude_rest: bool
        + exclude_initial_hyperventilation: bool
    }
}

package "Service" {
    class MetabolismAnalyzer {
        - config: AnalysisConfig
        - warnings: List[str]
        + analyze(breath_data): MetabolismAnalysisResult
        - _apply_phase_trimming()
        - _apply_gas_transport_delay()
        - _filter_local_outliers()
        - _power_binning()
        - _loess_smoothing()
        - _polynomial_fit()
        - _calculate_fatmax()
    }
}

' Relationships
MetabolismAnalyzer *-- AnalysisConfig : uses
MetabolismAnalyzer ..> MetabolismAnalysisResult : produces
MetabolismAnalysisResult *-- ProcessedSeries
MetabolismAnalysisResult *-- MetabolicMarkers
MetabolicMarkers *-- FatMaxMarker
MetabolicMarkers *-- CrossoverMarker
ProcessedSeries o-- ProcessedDataPoint

@enduml


@startuml
skinparam ActivityBackgroundColor #FEFEFE
skinparam ActivityBorderColor #333
skinparam ActivityDiamondBackgroundColor #White
skinparam ArrowColor #555

start
:<b>Input:</b> Raw Breath Data List;

partition "1. Pre-Analysis Filtering" {
    :<b>Phase Trimming</b>
    - Exclude Rest/Warm-up/Recovery
    - Handle Initial Hyperventilation;
    
    if (Data < 10 points?) then (yes)
        :Return None (Insufficient Data);
        stop
    else (no)
    endif
}

partition "2. Advanced Correction" {
    :<b>Gas Transport Delay Correction</b>
    - Time Shift VO2/VCO2 (-15s)
    - Re-align with Power;
    
    :<b>Rolling IQR Outlier Detection</b>
    - Window: 30s
    - Filter Spikes (Median ± 2*IQR);
}

partition "3. Data Aggregation" {
    :<b>Extract Raw Points</b>;
    
    :<b>Power Binning (10W)</b>
    - Group by Power
    - Method: Median / Trimmed Mean
    - Clamp Non-negative values;
}

partition "4. Smoothing & Modeling" {
    :<b>LOESS Smoothing</b>
    - Apply to Fat/CHO/RER/VO2
    - Fraction: 0.15 ~ 0.25;
    
    :<b>Polynomial Trend Fit</b>
    - Fat/CHO/RER: Degree 3
    - VO2/HR: Degree 2;
    note right
        <b>Sparse Data Handling:</b>
        Skip trend generation for
        power gaps > 30W
    end note
}

partition "5. Marker Calculation" {
    :<b>Calculate FatMax</b>
    - Find Peak Fat Oxidation (MFO)
    - Determine Zone (90% of MFO);
    
    :<b>Calculate Crossover</b>
    - Find intersection (Fat = CHO)
    - Linear Interpolation;
}

:<b>Construct Result</b>
- Processed Series (Raw, Binned, Smooth, Trend)
- Metabolic Markers (FatMax, Crossover);

stop
@enduml