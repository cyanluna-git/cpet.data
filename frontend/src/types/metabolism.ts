/**
 * Metabolism Analysis Types
 * - Configuration for analysis parameters
 * - State management for persistence
 */

// ============================================================================
// Backend API Types (matching backend/app/schemas/processed_metabolism.py)
// ============================================================================

/**
 * Analysis configuration for metabolism processing
 * Matches backend MetabolismConfig schema
 */
export interface MetabolismConfig {
  // Binning parameters
  bin_size: number;              // 5-30W, default 10
  aggregation_method: 'median' | 'mean' | 'trimmed_mean';

  // Smoothing parameters
  loess_frac: number;            // 0.1-0.5, default 0.25
  smoothing_method: 'loess' | 'savgol' | 'moving_avg';

  // Phase trimming
  exclude_rest: boolean;
  exclude_warmup: boolean;
  exclude_recovery: boolean;
  min_power_threshold: number | null;  // 0-200W, null means no threshold

  // Time-based trimming (analysis window)
  trim_start_sec: number | null;       // Manual trim start (seconds)
  trim_end_sec: number | null;         // Manual trim end (seconds)

  // FatMax zone
  fatmax_zone_threshold: number;       // 0.5-1.0, default 0.90
}

/**
 * Default configuration values
 */
export const DEFAULT_METABOLISM_CONFIG: MetabolismConfig = {
  bin_size: 10,
  aggregation_method: 'median',
  loess_frac: 0.25,
  smoothing_method: 'loess',
  exclude_rest: true,
  exclude_warmup: true,
  exclude_recovery: true,
  min_power_threshold: null,
  trim_start_sec: null,
  trim_end_sec: null,
  fatmax_zone_threshold: 0.90,
};

/**
 * Response from processed metabolism API
 */
export interface ProcessedMetabolismResponse {
  id: string | null;
  cpet_test_id: string;
  config: MetabolismConfig;
  is_manual_override: boolean;

  // Processed series data
  processed_series: {
    raw: ProcessedDataPoint[];
    binned: ProcessedDataPoint[];
    smoothed: ProcessedDataPoint[];
    trend?: ProcessedDataPoint[];
  } | null;

  // Metabolic markers
  metabolic_markers: {
    fat_max: {
      power: number;
      mfo: number;
      zone_min: number;
      zone_max: number;
    };
    crossover: {
      power: number | null;
      fat_value: number | null;
      cho_value: number | null;
    };
  } | null;

  // Stats
  stats: {
    total_data_points: number;
    exercise_data_points: number;
    binned_data_points: number;
  } | null;

  // Trim range info
  trim_range: {
    start_sec: number;
    end_sec: number;
    auto_detected: boolean;
    max_power_sec?: number;
  } | null;

  // Processing metadata
  processing_warnings: string[] | null;
  processing_status: string;
  processed_at: string | null;

  // Persistence state
  is_persisted: boolean;

  // Timestamps
  created_at: string | null;
  updated_at: string | null;
}

/**
 * Processed data point
 */
export interface ProcessedDataPoint {
  power: number;
  fat_oxidation: number | null;
  cho_oxidation: number | null;
  rer?: number | null;
  count?: number;  // for binned data
}

// ============================================================================
// Frontend State Management Types
// ============================================================================

/**
 * Analysis state for tracking server vs local config
 */
export interface AnalysisState {
  // Configuration from server (saved in DB or default)
  serverConfig: MetabolismConfig;

  // Local configuration being edited by user
  localConfig: MetabolismConfig;

  // Is there unsaved changes?
  isDirty: boolean;

  // Is the data persisted in DB?
  isServerPersisted: boolean;

  // Server response data (for display)
  serverData: ProcessedMetabolismResponse | null;
}

/**
 * Create initial analysis state
 */
export function createInitialAnalysisState(
  response?: ProcessedMetabolismResponse | null
): AnalysisState {
  const config = response?.config ?? { ...DEFAULT_METABOLISM_CONFIG };

  return {
    serverConfig: config,
    localConfig: { ...config },
    isDirty: false,
    isServerPersisted: response?.is_persisted ?? false,
    serverData: response ?? null,
  };
}

/**
 * Check if two configs are equal
 */
export function isConfigEqual(a: MetabolismConfig, b: MetabolismConfig): boolean {
  return (
    a.bin_size === b.bin_size &&
    a.aggregation_method === b.aggregation_method &&
    a.loess_frac === b.loess_frac &&
    a.smoothing_method === b.smoothing_method &&
    a.exclude_rest === b.exclude_rest &&
    a.exclude_warmup === b.exclude_warmup &&
    a.exclude_recovery === b.exclude_recovery &&
    a.min_power_threshold === b.min_power_threshold &&
    a.trim_start_sec === b.trim_start_sec &&
    a.trim_end_sec === b.trim_end_sec &&
    a.fatmax_zone_threshold === b.fatmax_zone_threshold
  );
}

/**
 * Validate config before saving
 */
export interface ConfigValidationResult {
  valid: boolean;
  errors: string[];
}

export function validateConfig(config: MetabolismConfig): ConfigValidationResult {
  const errors: string[] = [];

  // Validate bin_size
  if (config.bin_size < 5 || config.bin_size > 30) {
    errors.push('Bin size must be between 5 and 30W');
  }

  // Validate loess_frac
  if (config.loess_frac < 0.1 || config.loess_frac > 0.5) {
    errors.push('LOESS fraction must be between 0.1 and 0.5');
  }

  // Validate min_power_threshold
  if (config.min_power_threshold !== null) {
    if (config.min_power_threshold < 0 || config.min_power_threshold > 200) {
      errors.push('Min power threshold must be between 0 and 200W');
    }
  }

  // Validate trim range
  if (config.trim_start_sec !== null && config.trim_end_sec !== null) {
    if (config.trim_end_sec <= config.trim_start_sec) {
      errors.push('Trim end must be greater than trim start');
    }
    const duration = config.trim_end_sec - config.trim_start_sec;
    if (duration < 180) {
      errors.push('Trim range must be at least 180 seconds (3 minutes)');
    }
  }

  // Validate fatmax_zone_threshold
  if (config.fatmax_zone_threshold < 0.5 || config.fatmax_zone_threshold > 1.0) {
    errors.push('FatMax zone threshold must be between 0.5 and 1.0');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Format seconds to mm:ss display
 */
export function formatSecondsToMMSS(seconds: number | null): string {
  if (seconds === null) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Parse mm:ss to seconds
 */
export function parseMMSSToSeconds(value: string): number | null {
  const match = value.match(/^(\d+):(\d{2})$/);
  if (!match) return null;
  const mins = parseInt(match[1], 10);
  const secs = parseInt(match[2], 10);
  if (secs >= 60) return null;
  return mins * 60 + secs;
}
