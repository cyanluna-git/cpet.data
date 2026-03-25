/**
 * EnergySystemTab - 3-pathway Energy System Analysis display
 *
 * Shows PieChart of oxidative/glycolytic/phosphagen energy contributions
 * plus detail table and recovery phase manual override slider.
 */

import { useState, useEffect, useCallback } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Save, AlertTriangle, Loader2 } from 'lucide-react';
import { api, type EnergySystemResponse } from '@/lib/api';
import { toast } from 'sonner';

interface EnergySystemTabProps {
  testId: string;
  canEdit: boolean;
  totalDurationSec: number;
}

export function EnergySystemTab({ testId, canEdit, totalDurationSec }: EnergySystemTabProps) {
  const [data, setData] = useState<EnergySystemResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Recovery override state
  const [recoveryStart, setRecoveryStart] = useState<number | null>(null);
  const [recoveryEnd, setRecoveryEnd] = useState<number | null>(null);
  const [isOverrideActive, setIsOverrideActive] = useState(false);

  // Load energy system data
  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getEnergySystem(testId);
        setData(result);
        // Initialize recovery slider from server
        if (result.recovery_window) {
          setRecoveryStart(result.recovery_window.start_sec);
          setRecoveryEnd(result.recovery_window.end_sec);
          setIsOverrideActive(result.recovery_window.is_manual_override);
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to load energy system data';
        setError(message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [testId]);

  // Recalculate with override
  const handleRecalculate = useCallback(async () => {
    if (!recoveryStart || !recoveryEnd) return;

    setLoading(true);
    try {
      const result = await api.calculateEnergySystem(testId, {
        recovery_start_sec: recoveryStart,
        recovery_end_sec: recoveryEnd,
        save: false,
      });
      setData(result);
      setIsOverrideActive(true);
    } catch (err: unknown) {
      toast.error('Recalculation failed');
    } finally {
      setLoading(false);
    }
  }, [testId, recoveryStart, recoveryEnd]);

  // Save with override
  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const result = await api.calculateEnergySystem(testId, {
        recovery_start_sec: isOverrideActive ? recoveryStart : undefined,
        recovery_end_sec: isOverrideActive ? recoveryEnd : undefined,
        save: true,
      });
      setData(result);
      toast.success('Energy system analysis saved');
    } catch (err: unknown) {
      toast.error('Save failed');
    } finally {
      setSaving(false);
    }
  }, [testId, recoveryStart, recoveryEnd, isOverrideActive]);

  if (loading) {
    return (
      <div className="report-section mb-8 border-none p-8">
        <div className="flex items-center justify-center gap-2 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>에너지 시스템 분석 중...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="report-section mb-8 border-none p-8 text-center">
        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-2" />
        <p className="text-gray-600">{error}</p>
      </div>
    );
  }

  if (!data || data.pathways.length === 0) {
    return (
      <div className="report-section mb-8 border-none p-8 text-center">
        <p className="text-gray-500">에너지 시스템 분석 데이터가 없습니다.</p>
      </div>
    );
  }

  const pieData = data.pathways.map(p => ({
    name: p.name,
    value: p.energy_kj,
    percentage: p.percentage,
    color: p.color,
  }));

  const formatKJ = (v: number | null): string =>
    v !== null ? `${v.toFixed(1)} kJ` : '-';
  const formatPct = (v: number | null): string =>
    v !== null ? `${v.toFixed(1)}%` : '-';
  const formatSec = (s: number): string => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const hasLowR2 = data.mono_exp_fit && data.mono_exp_fit.r_squared < 0.8;

  return (
    <div className="space-y-6">
      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="rounded-[18px] border border-[rgba(161,123,55,0.25)] bg-[rgba(161,123,55,0.08)] p-3">
          {data.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-amber-800">
              <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Main content: Pie chart + Detail table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart */}
        <div className="report-section border-none p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            에너지 시스템 기여도
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percentage }) =>
                    `${name} ${percentage !== null ? percentage.toFixed(1) : '?'}%`
                  }
                  labelLine={true}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [
                    `${value.toFixed(1)} kJ`,
                    name,
                  ]}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {data.total_kj && (
            <p className="text-center text-sm text-gray-600 mt-2">
              Total: {data.total_kj.toFixed(1)} kJ
            </p>
          )}
        </div>

        {/* Detail Table */}
        <div className="report-section border-none p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            경로별 상세
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-2 text-gray-600 font-medium">Pathway</th>
                <th className="text-right py-2 text-gray-600 font-medium">Energy</th>
                <th className="text-right py-2 text-gray-600 font-medium">%</th>
              </tr>
            </thead>
            <tbody>
              {data.pathways.map((p) => (
                <tr key={p.name} className="border-b border-gray-100">
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: p.color }}
                      />
                      <span className="font-medium text-gray-900">{p.name}</span>
                    </div>
                  </td>
                  <td className="text-right py-3 text-gray-700">
                    {formatKJ(p.energy_kj)}
                  </td>
                  <td className="text-right py-3 font-semibold text-gray-900">
                    {formatPct(p.percentage)}
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 border-gray-300">
                <td className="py-3 font-semibold text-gray-900">Total</td>
                <td className="text-right py-3 font-semibold text-gray-900">
                  {formatKJ(data.total_kj)}
                </td>
                <td className="text-right py-3 font-semibold text-gray-900">
                  100%
                </td>
              </tr>
            </tbody>
          </table>

          {/* Additional info */}
          <div className="mt-4 space-y-2 text-xs text-gray-500">
            {data.delta_lactate !== null && (
              <p>Delta Lactate: {data.delta_lactate.toFixed(2)} mmol/L</p>
            )}
            {data.exercise_duration_sec && (
              <p>Exercise Duration: {formatSec(data.exercise_duration_sec)}</p>
            )}
            {data.body_weight_kg && (
              <p>Body Weight: {data.body_weight_kg.toFixed(1)} kg</p>
            )}
          </div>

          {/* Mono-exp fit details */}
          {data.mono_exp_fit && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg">
              <p className="text-xs font-medium text-gray-700 mb-1">
                Recovery VO2 Fit (Mono-exponential)
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
                <span>Amplitude: {data.mono_exp_fit.amplitude_l_min.toFixed(3)} L/min</span>
                <span>Tau: {data.mono_exp_fit.tau_sec.toFixed(1)} s</span>
                <span>Baseline: {data.mono_exp_fit.baseline_l_min.toFixed(3)} L/min</span>
                <span className={hasLowR2 ? 'text-amber-600 font-medium' : ''}>
                  R²: {data.mono_exp_fit.r_squared.toFixed(4)}
                  {hasLowR2 && ' (low)'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Recovery Phase Override */}
      {canEdit && totalDurationSec > 0 && (
        <div className="report-section border-none p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Recovery Phase Override
          </h3>
          <p className="text-xs text-gray-500 mb-4">
            Adjust the recovery window to improve phosphagen (PCr) energy estimation.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-600">
                Recovery Start: {recoveryStart !== null ? formatSec(recoveryStart) : '--:--'}
              </label>
              <Slider
                value={[recoveryStart ?? 0]}
                onValueChange={([v]) => setRecoveryStart(v)}
                min={0}
                max={totalDurationSec}
                step={1}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-600">
                Recovery End: {recoveryEnd !== null ? formatSec(recoveryEnd) : '--:--'}
              </label>
              <Slider
                value={[recoveryEnd ?? totalDurationSec]}
                onValueChange={([v]) => setRecoveryEnd(v)}
                min={0}
                max={totalDurationSec}
                step={1}
                className="w-full"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRecalculate}
              disabled={loading || !recoveryStart || !recoveryEnd || recoveryEnd <= recoveryStart}
            >
              Recalculate
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="gap-1"
            >
              {saving ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Save className="w-3 h-3" />
              )}
              Save
            </Button>
          </div>
        </div>
      )}

      {/* No-lactate / No-phosphagen info boxes */}
      {!data.has_lactate && (
        <div className="rounded-[18px] border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
          <p className="font-medium mb-1">Glycolytic pathway not available</p>
          <p>
            Blood lactate data is required for glycolytic energy estimation.
            Upload blood samples via the Blood Samples API to enable 3-pathway analysis.
          </p>
        </div>
      )}

      {!data.has_phosphagen && (
        <div className="rounded-[18px] border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
          <p className="font-medium mb-1">Phosphagen pathway not available</p>
          <p>
            Sufficient recovery phase data is required for phosphagen (PCr) energy estimation.
            Ensure the test includes at least 30 seconds of recovery after exercise cessation.
          </p>
        </div>
      )}
    </div>
  );
}
