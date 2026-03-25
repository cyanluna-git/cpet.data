/**
 * Energy System 3-Pathway Analysis Types
 *
 * Matches backend app/api/energy_system.py response schemas
 */

export interface EnergyPathway {
  name: 'Oxidative' | 'Glycolytic' | 'Phosphagen';
  energy_kj: number;
  percentage: number | null;
  color: string;
}

export interface MonoExpFit {
  amplitude_l_min: number;
  tau_sec: number;
  baseline_l_min: number;
  r_squared: number;
  n_points: number;
}

export interface RecoveryWindowInfo {
  start_sec: number;
  end_sec: number;
  is_manual_override: boolean;
}

export interface EnergySystemResponse {
  pathways: EnergyPathway[];
  total_kj: number | null;
  has_lactate: boolean;
  has_phosphagen: boolean;
  delta_lactate: number | null;
  exercise_duration_sec: number | null;
  body_weight_kg: number | null;
  mono_exp_fit: MonoExpFit | null;
  recovery_window: RecoveryWindowInfo | null;
  warnings: string[];
}

export interface EnergySystemRequest {
  recovery_start_sec?: number | null;
  recovery_end_sec?: number | null;
  exercise_start_sec?: number | null;
  exercise_end_sec?: number | null;
  save?: boolean;
}

export interface BloodSample {
  id: string;
  cpet_test_id: string;
  block: string | null;
  step: string | null;
  load_w: number | null;
  ftp_pct: string | null;
  duration_min: number | null;
  sample_time_kst: string | null;
  elapsed_sec: number | null;
  hr_bpm: number | null;
  lactate_mmol: number | null;
  glucose_mmol: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BloodSampleListResponse {
  cpet_test_id: string;
  samples: BloodSample[];
  total: number;
  resting_lactate: number | null;
  peak_lactate: number | null;
  delta_lactate: number | null;
}
