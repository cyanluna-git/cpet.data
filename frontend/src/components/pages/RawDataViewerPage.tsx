import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Database, Download, ChevronLeft, ChevronRight, Settings2, Check, User, Calendar, LineChart, X, Scissors, Save, RotateCcw, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage, getAuthToken } from '@/utils/apiHelpers';
import { useDebounce } from '@/hooks/useDebounce';
import { Slider } from '@/components/ui/slider';
import { api, API_BASE, type MetabolismConfigApi } from '@/lib/api';
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  ReferenceLine,
  ReferenceArea,
  Label,
} from 'recharts';

interface RawDataViewerPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

interface TestOption {
  test_id: string;
  source_filename: string;
  test_date: string;
  subject_id: string;
  subject_name?: string;
  protocol_type?: string;
  is_valid?: boolean;
}

interface SubjectOption {
  id: string;
  name: string;
  research_id: string;
}

interface BreathDataRow {
  id: number;
  time: string;
  t_sec: number | null;
  rf: number | null;
  vt: number | null;
  vo2: number | null;
  vco2: number | null;
  ve: number | null;
  hr: number | null;
  vo2_hr: number | null;
  bike_power: number | null;
  bike_torque: number | null;
  cadence: number | null;
  feo2: number | null;
  feco2: number | null;
  feto2: number | null;
  fetco2: number | null;
  ve_vo2: number | null;
  ve_vco2: number | null;
  rer: number | null;
  fat_oxidation: number | null;
  cho_oxidation: number | null;
  vo2_rel: number | null;
  mets: number | null;
  ee_total: number | null;
  phase: string | null;
  data_source: string | null;
  is_valid: boolean;
}

interface RawDataResponse {
  test_id: string;
  source_filename: string;
  test_date: string;
  subject_name: string | null;
  total_rows: number;
  data: BreathDataRow[];
}

// 컬럼 그룹 정의
interface ColumnDef {
  key: string;
  label: string;
  group: 'fixed' | 'basic' | 'respiratory' | 'metabolic' | 'cardio';
  format: (v: any) => string;
}

// 고정 컬럼 (항상 왼쪽에 표시)
const FIXED_COLUMNS: ColumnDef[] = [
  { key: 't_sec', label: 'Time(s)', group: 'fixed', format: (v: number | null) => v?.toFixed(0) ?? '-' },
  { key: 'phase', label: 'Phase', group: 'fixed', format: (v: string | null) => v ?? '-' },
];

// 선택 가능한 컬럼 (그룹별 정의)
const SELECTABLE_COLUMNS: ColumnDef[] = [
  // 기본 지표
  { key: 'hr', label: 'HR', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'bike_power', label: 'Power(W)', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'cadence', label: 'Cadence', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'mets', label: 'METs', group: 'basic', format: (v: number | null) => v?.toFixed(1) ?? '-' },

  // 호흡 지표
  { key: 've', label: 'VE', group: 'respiratory', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vt', label: 'VT', group: 'respiratory', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'rf', label: 'RF', group: 'respiratory', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'feto2', label: 'FetO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'fetco2', label: 'FetCO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'feo2', label: 'FeO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'feco2', label: 'FeCO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },

  // 대사 지표
  { key: 'vo2', label: 'VO2', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vco2', label: 'VCO2', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'rer', label: 'RER', group: 'metabolic', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'fat_oxidation', label: 'Fat(g/min)', group: 'metabolic', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'cho_oxidation', label: 'CHO(g/min)', group: 'metabolic', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'vo2_rel', label: 'VO2/kg', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'ee_total', label: 'EE', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },

  // 심폐 지표
  { key: 'vo2_hr', label: 'VO2/HR', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 've_vo2', label: 'VE/VO2', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 've_vco2', label: 'VE/VCO2', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'bike_torque', label: 'Torque', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
];

// 그룹 정보
const COLUMN_GROUPS = {
  basic: { label: '기본', color: 'bg-blue-100 text-blue-800' },
  respiratory: { label: '호흡', color: 'bg-green-100 text-green-800' },
  metabolic: { label: '대사', color: 'bg-orange-100 text-orange-800' },
  cardio: { label: '심폐', color: 'bg-purple-100 text-purple-800' },
};

// 기본 선택 컬럼
const DEFAULT_SELECTED_COLUMNS = ['hr', 'vo2', 'vco2', 've', 'rer', 'fat_oxidation', 'cho_oxidation', 'bike_power', 'mets'];

// 차트용 컬럼 정의 (숫자형만)
const CHART_COLUMNS = [
  { key: 't_sec', label: 'Time(s)', unit: 's' },
  { key: 'hr', label: 'HR', unit: 'bpm' },
  { key: 'bike_power', label: 'Power', unit: 'W' },
  { key: 'cadence', label: 'Cadence', unit: 'rpm' },
  { key: 'mets', label: 'METs', unit: '' },
  { key: 've', label: 'VE', unit: 'L/min' },
  { key: 'vt', label: 'VT', unit: 'L' },
  { key: 'rf', label: 'RF', unit: '/min' },
  { key: 'vo2', label: 'VO2', unit: 'mL/min' },
  { key: 'vco2', label: 'VCO2', unit: 'mL/min' },
  { key: 'rer', label: 'RER', unit: '' },
  { key: 'fat_oxidation', label: 'Fat', unit: 'g/min' },
  { key: 'cho_oxidation', label: 'CHO', unit: 'g/min' },
  { key: 'vo2_rel', label: 'VO2/kg', unit: 'mL/kg/min' },
  { key: 'vo2_hr', label: 'VO2/HR', unit: 'mL/beat' },
  { key: 've_vo2', label: 'VE/VO2', unit: '' },
  { key: 've_vco2', label: 'VE/VCO2', unit: '' },
];

// 차트 색상
const CHART_COLORS = [
  '#2563EB', // blue
  '#DC2626', // red
  '#16A34A', // green
  '#CA8A04', // yellow
  '#9333EA', // purple
  '#0891B2', // cyan
  '#EA580C', // orange
  '#DB2777', // pink
];

// 데이터 키별 고정 색상 (교수님 차트 기준)
const DATA_KEY_COLORS: Record<string, string> = {
  fat_oxidation: '#DC2626', // 빨강 (Fat)
  cho_oxidation: '#16A34A', // 녹색 (CHO)
  vo2_rel: '#2563EB', // 파랑 (VO2/kg)
  hr: '#DC2626', // 빨강 (HR)
  vo2: '#2563EB', // 파랑 (VO2)
  vco2: '#16A34A', // 녹색 (VCO2)
  rer: '#CA8A04', // 노랑 (RER)
  ve: '#9333EA', // 보라 (VE)
  bike_power: '#EA580C', // 주황 (Power)
};

// 색상 가져오기 (고정 색상 우선, 없으면 인덱스 기반)
const getDataColor = (key: string, fallbackIndex: number) => {
  return DATA_KEY_COLORS[key] || CHART_COLORS[fallbackIndex % CHART_COLORS.length];
};

const CHART_PRESETS = [
  {
    key: 'fatmax',
    label: 'FATMAX',
    x: 'bike_power',
    yLeft: ['fat_oxidation', 'cho_oxidation'],
    yRight: ['vo2_rel'],
    xUnit: 'W',
    yLeftUnit: 'g/min',
    yRightUnit: 'ml/min/kg',
    description: 'Fat & CHO oxidation with VO2/kg vs Power',
  },
  {
    key: 'rer',
    label: 'RER Curve',
    x: 'bike_power',
    yLeft: ['rer'],
    yRight: [],
    xUnit: 'W',
    yLeftUnit: 'Ratio',
    yRightUnit: '',
    description: 'Respiratory Exchange Ratio vs Power',
  },
  {
    key: 'vo2',
    label: 'VO2 Kinetics',
    x: 'bike_power',
    yLeft: ['vo2', 'vco2'],
    yRight: ['hr'],
    xUnit: 'W',
    yLeftUnit: 'mL/min',
    yRightUnit: 'bpm',
    description: 'VO2/VCO2 and HR vs Power',
  },
  {
    key: 'vt',
    label: 'VT Analysis',
    x: 'vo2',
    yLeft: ['ve_vo2', 've_vco2'],
    yRight: [],
    xUnit: 'mL/min',
    yLeftUnit: 'Eq. Ratio',
    yRightUnit: '',
    description: 'Ventilatory Equivalents vs VO2',
  },
  {
    key: 'custom',
    label: 'Custom',
    x: 't_sec',
    yLeft: [],
    yRight: [],
    xUnit: 'sec',
    yLeftUnit: '',
    yRightUnit: '',
    description: 'Custom chart configuration',
  },
];

const QUAD_PRESETS = CHART_PRESETS.filter((preset) => preset.key !== 'custom');

// Stable tooltip formatters (defined outside component to prevent re-creation)
const tooltipFormatter = (value: any, name: string) => {
  const col = CHART_COLUMNS.find(c => c.key === name);
  return [typeof value === 'number' ? value.toFixed(2) : value, col?.label || name];
};

const overviewTooltipFormatter = (value: any, name: string) => {
  const col = CHART_COLUMNS.find(c => c.key === name);
  return [typeof value === 'number' ? value.toFixed(1) : value, col?.label || name];
};

const overviewLabelFormatter = (label: any) =>
  `Time(s): ${typeof label === 'number' ? label.toFixed(0) : label}`;

const numberTickFormatter = (v: any) => typeof v === 'number' ? v.toFixed(0) : v;

// PresetChart component - memoized to prevent unnecessary re-renders
interface PresetChartProps {
  preset: typeof QUAD_PRESETS[number];
  presetIndex: number;
  chartData: any[];
  isProcessed: boolean;
  dataMode: 'raw' | 'smoothed' | 'trend';
  analysisData: any;
}

const PresetChart = React.memo(({ preset, presetIndex, chartData, isProcessed, dataMode, analysisData }: PresetChartProps) => {
  const xLabel = CHART_COLUMNS.find(c => c.key === preset.x)?.label || preset.x;

  const labelFormatter = useCallback(
    (label: any) => `${xLabel}: ${typeof label === 'number' ? label.toFixed(1) : label}`,
    [xLabel]
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-700">{preset.label}</span>
        <span className="text-[11px] text-gray-400">X: {xLabel}</span>
      </div>
      {chartData.length === 0 ? (
        <div className="aspect-square w-full flex items-center justify-center text-xs text-gray-400">
          데이터 없음
        </div>
      ) : (
        <div className="aspect-[4/3] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }} syncId="rawDataViewer">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey={preset.x}
                type="number"
                domain={['dataMin', 'dataMax']}
                tick={{ fontSize: 10 }}
                tickFormatter={numberTickFormatter}
                label={preset.xUnit ? { value: preset.xUnit, position: 'insideBottomRight', offset: -5, style: { fontSize: 10, fill: '#6b7280' } } : undefined}
              />
              <YAxis
                yAxisId="left"
                type="number"
                domain={preset.key === 'rer' ? [0.6, 1.2] : ['auto', 'auto']}
                allowDataOverflow={preset.key === 'rer'}
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => typeof v === 'number' ? (preset.key === 'rer' ? v.toFixed(2) : preset.key === 'fatmax' ? v.toFixed(2) : v.toFixed(0)) : v}
                label={preset.yLeftUnit ? { value: preset.yLeftUnit, angle: -90, position: 'insideLeft', style: { fontSize: 10, fill: '#6b7280' } } : undefined}
              />
              {preset.yRight.length > 0 && (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  type="number"
                  domain={['auto', 'auto']}
                  tick={{ fontSize: 10 }}
                  tickFormatter={numberTickFormatter}
                  label={preset.yRightUnit ? { value: preset.yRightUnit, angle: 90, position: 'insideRight', style: { fontSize: 10, fill: '#6b7280' } } : undefined}
                />
              )}
              <ZAxis range={[20, 20]} />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={tooltipFormatter}
                labelFormatter={labelFormatter}
              />
              {/* FatMax Zone (90% MFO range) */}
              {analysisData?.metabolic_markers?.fat_max?.zone_min &&
                analysisData?.metabolic_markers?.fat_max?.zone_max &&
                preset.key === 'fatmax' && (
                  <ReferenceArea
                    x1={analysisData.metabolic_markers.fat_max.zone_min}
                    x2={analysisData.metabolic_markers.fat_max.zone_max}
                    yAxisId="left"
                    fill="#3B82F6"
                    fillOpacity={0.1}
                    stroke="#3B82F6"
                    strokeOpacity={0.3}
                    strokeDasharray="3 3"
                  />
                )}
              {/* FatMax line */}
              {analysisData?.metabolic_markers?.fat_max?.power && preset.key === 'fatmax' && (
                <ReferenceLine
                  x={analysisData.metabolic_markers.fat_max.power}
                  yAxisId="left"
                  stroke="#DC2626"
                  strokeDasharray="5 5"
                  strokeWidth={2}
                >
                  <Label
                    value={`FatMax ${analysisData.metabolic_markers.fat_max.power}W`}
                    position="top"
                    dy={-5}
                    fill="#DC2626"
                    fontSize={11}
                    fontWeight={600}
                  />
                </ReferenceLine>
              )}
              {/* Crossover line */}
              {analysisData?.metabolic_markers?.crossover?.power && preset.key === 'fatmax' && (
                <ReferenceLine
                  x={analysisData.metabolic_markers.crossover.power}
                  yAxisId="left"
                  stroke="#8B5CF6"
                  strokeDasharray="3 3"
                  strokeWidth={2}
                >
                  <Label
                    value={`Crossover ${analysisData.metabolic_markers.crossover.power}W`}
                    position="insideTop"
                    dy={15}
                    fill="#8B5CF6"
                    fontSize={10}
                  />
                </ReferenceLine>
              )}
              {/* VT1 and VT2 reference lines */}
              {analysisData?.vt1_vo2 && preset.key === 'vt' && (
                <ReferenceLine
                  x={analysisData.vt1_vo2}
                  yAxisId="left"
                  stroke="#22C55E"
                  strokeDasharray="4 4"
                  strokeWidth={2}
                >
                  <Label value="VT1" position="top" fill="#22C55E" fontSize={11} />
                </ReferenceLine>
              )}
              {analysisData?.vt2_vo2 && preset.key === 'vt' && (
                <ReferenceLine
                  x={analysisData.vt2_vo2}
                  yAxisId="left"
                  stroke="#EF4444"
                  strokeDasharray="4 4"
                  strokeWidth={2}
                >
                  <Label value="VT2" position="top" fill="#EF4444" fontSize={11} />
                </ReferenceLine>
              )}
              {isProcessed ? (
                <>
                  {preset.yLeft.map((key, idx) => {
                    const col = CHART_COLUMNS.find(c => c.key === key);
                    const color = getDataColor(key, presetIndex + idx);
                    return (
                      <React.Fragment key={`${preset.key}-left-${key}-group`}>
                        {dataMode === 'trend' && (
                          <Line
                            yAxisId="left"
                            type="monotone"
                            dataKey={`${key}_smooth`}
                            stroke={color}
                            strokeWidth={1.5}
                            strokeOpacity={0.3}
                            strokeDasharray="6 4"
                            dot={false}
                            isAnimationActive={false}
                            connectNulls
                          />
                        )}
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey={key}
                          name={col?.label || key}
                          stroke={color}
                          strokeWidth={dataMode === 'trend' ? 3.5 : 2.5}
                          dot={false}
                          connectNulls
                        />
                      </React.Fragment>
                    );
                  })}
                  {preset.yRight.map((key, idx) => {
                    const col = CHART_COLUMNS.find(c => c.key === key);
                    const color = getDataColor(key, presetIndex + preset.yLeft.length + idx);
                    return (
                      <React.Fragment key={`${preset.key}-right-${key}-group`}>
                        {dataMode === 'trend' && (
                          <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey={`${key}_smooth`}
                            stroke={color}
                            strokeWidth={1}
                            strokeOpacity={0.3}
                            strokeDasharray="6 4"
                            dot={false}
                            isAnimationActive={false}
                            connectNulls
                          />
                        )}
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey={key}
                          name={col?.label || key}
                          stroke={color}
                          strokeWidth={dataMode === 'trend' ? 2.5 : 2}
                          dot={false}
                          connectNulls
                        />
                      </React.Fragment>
                    );
                  })}
                </>
              ) : (
                <>
                  {preset.yLeft.map((key, idx) => {
                    const col = CHART_COLUMNS.find(c => c.key === key);
                    const color = getDataColor(key, presetIndex + idx);
                    return (
                      <Scatter
                        key={`${preset.key}-left-${key}`}
                        yAxisId="left"
                        dataKey={key}
                        name={col?.label || key}
                        fill={color}
                        line={{ stroke: color, strokeWidth: 1 }}
                        lineType="joint"
                      />
                    );
                  })}
                  {preset.yRight.map((key, idx) => {
                    const col = CHART_COLUMNS.find(c => c.key === key);
                    const color = getDataColor(key, presetIndex + preset.yLeft.length + idx);
                    return (
                      <Scatter
                        key={`${preset.key}-right-${key}`}
                        yAxisId="right"
                        dataKey={key}
                        name={col?.label || key}
                        fill={color}
                        line={{ stroke: color, strokeWidth: 1, strokeDasharray: '5 5' }}
                        lineType="joint"
                        shape="cross"
                      />
                    );
                  })}
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-2 text-[11px] text-gray-400">
        Y-left: {preset.yLeft.map(k => CHART_COLUMNS.find(c => c.key === k)?.label).join(', ')}
        {preset.yRight.length > 0 && (
          <> · Y-right: {preset.yRight.map(k => CHART_COLUMNS.find(c => c.key === k)?.label).join(', ')}</>
        )}
      </div>
    </div>
  );
});

const PAGE_SIZE = 50;

export function RawDataViewerPage({ user, onLogout, onNavigate }: RawDataViewerPageProps) {
  // 피험자 및 테스트 상태
  const [subjects, setSubjects] = useState<SubjectOption[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>('');
  const [tests, setTests] = useState<TestOption[]>([]);
  const [filteredTests, setFilteredTests] = useState<TestOption[]>([]);
  const [selectedTestId, setSelectedTestId] = useState<string>('');
  const [rawData, setRawData] = useState<RawDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSubjects, setLoadingSubjects] = useState(true);
  const [loadingTests, setLoadingTests] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  // 전처리 데이터 상태 추가
  type DataMode = 'raw' | 'smoothed' | 'trend';
  const [dataMode, setDataMode] = useState<DataMode>('raw');
  const useProcessedData = dataMode !== 'raw'; // 호환성 유지
  const [processedData, setProcessedData] = useState<any>(null);
  const [analysisData, setAnalysisData] = useState<any>(null);

  // Analysis settings consolidated into a single object
  interface AnalysisSettings {
    loess: number;
    bin: number;
    method: 'median' | 'mean' | 'trimmed_mean';
    minPower: number;
  }
  const [analysisSettings, setAnalysisSettings] = useState<AnalysisSettings>({
    loess: 0.25,
    bin: 10,
    method: 'median',
    minPower: 0,
  });

  // Debounced values for API calls (prevents excessive requests during slider drag)
  const debouncedLoess = useDebounce(analysisSettings.loess, 500);
  const debouncedBin = useDebounce(analysisSettings.bin, 500);
  const debouncedMinPower = useDebounce(analysisSettings.minPower, 500);

  // Trim range state (for FATMAX analysis window)
  interface TrimRange {
    start: number;
    end: number;
  }
  const [trimRange, setTrimRange] = useState<TrimRange | null>(null);
  const [totalDuration, setTotalDuration] = useState<number>(600); // Default 10 min
  const debouncedTrimRange = useDebounce(trimRange, 500);

  // v1.2.0: VO2max segment range (for HYBRID protocol)
  const [vo2maxRange, setVo2maxRange] = useState<TrimRange | null>(null);
  const debouncedVo2maxRange = useDebounce(vo2maxRange, 500);

  // ========== Persistence State ==========
  // Server config: what's saved in DB (or default from server)
  interface ServerConfig {
    loess: number;
    bin: number;
    method: 'median' | 'mean' | 'trimmed_mean';
    minPower: number;
    trimStart: number | null;
    trimEnd: number | null;
    vo2maxStart: number | null;
    vo2maxEnd: number | null;
  }
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [isServerPersisted, setIsServerPersisted] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [persistenceLoaded, setPersistenceLoaded] = useState(false);

  // Calculate isDirty by comparing local state to server config
  const isDirty = useMemo(() => {
    // If persistence hasn't loaded yet, we can't determine dirty state
    if (!persistenceLoaded) {
      return false;
    }

    if (!isServerPersisted) {
      return true;
    }

    if (!serverConfig) {
      return false;
    }

    // Helper for floating point comparison with epsilon
    const floatEq = (a: number, b: number, epsilon = 0.001) => Math.abs(a - b) < epsilon;

    // Compare analysis settings
    const loessDiff = !floatEq(analysisSettings.loess, serverConfig.loess);
    const binDiff = analysisSettings.bin !== serverConfig.bin;
    const methodDiff = analysisSettings.method !== serverConfig.method;
    const minPowerDiff = analysisSettings.minPower !== serverConfig.minPower;

    // Compare trim range
    const localTrimStart = trimRange?.start ?? null;
    const localTrimEnd = trimRange?.end ?? null;

    const trimStartDiff =
      (localTrimStart === null && serverConfig.trimStart !== null) ||
      (localTrimStart !== null && serverConfig.trimStart === null) ||
      (localTrimStart !== null && serverConfig.trimStart !== null && !floatEq(localTrimStart, serverConfig.trimStart, 1));

    const trimEndDiff =
      (localTrimEnd === null && serverConfig.trimEnd !== null) ||
      (localTrimEnd !== null && serverConfig.trimEnd === null) ||
      (localTrimEnd !== null && serverConfig.trimEnd !== null && !floatEq(localTrimEnd, serverConfig.trimEnd, 1));

    // v1.2.0: VO2max segment comparison
    const localVo2maxStart = vo2maxRange?.start ?? null;
    const localVo2maxEnd = vo2maxRange?.end ?? null;

    const vo2maxStartDiff =
      (localVo2maxStart === null && serverConfig.vo2maxStart !== null) ||
      (localVo2maxStart !== null && serverConfig.vo2maxStart === null) ||
      (localVo2maxStart !== null && serverConfig.vo2maxStart !== null && !floatEq(localVo2maxStart, serverConfig.vo2maxStart, 1));

    const vo2maxEndDiff =
      (localVo2maxEnd === null && serverConfig.vo2maxEnd !== null) ||
      (localVo2maxEnd !== null && serverConfig.vo2maxEnd === null) ||
      (localVo2maxEnd !== null && serverConfig.vo2maxEnd !== null && !floatEq(localVo2maxEnd, serverConfig.vo2maxEnd, 1));

    return loessDiff || binDiff || methodDiff || minPowerDiff || trimStartDiff || trimEndDiff || vo2maxStartDiff || vo2maxEndDiff;
  }, [serverConfig, analysisSettings, trimRange, vo2maxRange, persistenceLoaded, isServerPersisted]);

  // 컬럼 선택 상태
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_SELECTED_COLUMNS);
  const [showColumnSelector, setShowColumnSelector] = useState(false);
  const columnSelectorRef = useRef<HTMLDivElement>(null);

  // 차트 상태
  const [showChart, setShowChart] = useState(true);
  const [showRawTable, setShowRawTable] = useState(false);

  // 외부 클릭 시 컬럼 선택기 닫기
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (columnSelectorRef.current && !columnSelectorRef.current.contains(event.target as Node)) {
        setShowColumnSelector(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 컬럼 토글
  const toggleColumn = useCallback((key: string) => {
    setSelectedColumns(prev =>
      prev.includes(key)
        ? prev.filter(k => k !== key)
        : [...prev, key]
    );
  }, []);

  // 그룹 전체 선택/해제
  const toggleGroup = useCallback((group: string) => {
    const groupColumns = SELECTABLE_COLUMNS.filter(c => c.group === group).map(c => c.key);
    const allSelected = groupColumns.every(k => selectedColumns.includes(k));

    if (allSelected) {
      setSelectedColumns(prev => prev.filter(k => !groupColumns.includes(k)));
    } else {
      setSelectedColumns(prev => [...new Set([...prev, ...groupColumns])]);
    }
  }, [selectedColumns]);

  // 현재 선택된 컬럼 (고정 + 선택된 컬럼)
  const displayColumns = [
    ...FIXED_COLUMNS,
    ...SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key))
  ];

  const rawChartData = useMemo(() => {
    if (!rawData) {
      return [];
    }
    const data = rawData.data;

    // Dynamic maxPoints based on data density and duration
    // For longer tests, allow more points to preserve detail
    const totalDuration = data.length > 0 && data[data.length - 1]?.t_sec
      ? data[data.length - 1].t_sec
      : data.length * 5; // Assume 5s intervals if no t_sec

    // Scale maxPoints with duration: 500 for 10min, up to 1000 for longer tests
    const maxPoints = Math.min(1000, Math.max(500, Math.floor((totalDuration ?? 600) / 1.2)));

    if (data.length <= maxPoints) {
      return data;
    }

    // Use uniform sampling that preserves data distribution
    const step = data.length / maxPoints;
    const sampled = [];
    for (let i = 0; i < maxPoints; i++) {
      const index = Math.floor(i * step);
      sampled.push(data[index]);
    }
    return sampled;
  }, [rawData]);

  const processedChartData = useMemo(() => {
    return processedData?.data || [];
  }, [processedData]);

  const getChartDataForPreset = useCallback(
    (xKey: string, yLeft: string[], yRight: string[]): { data: any[]; isProcessed: boolean } => {
      const allYKeys = [...yLeft, ...yRight];

      // Check if processed data has valid X-axis data and at least one Y-axis with non-null values
      const hasValidXAxis =
        processedChartData.length > 0 &&
        xKey in processedChartData[0] &&
        processedChartData.some((d: any) => d[xKey] !== null && d[xKey] !== undefined);

      // At least one Y-axis key should have valid data
      const hasValidYAxis =
        allYKeys.length === 0 ||
        allYKeys.some((key) =>
          processedChartData.some((d: any) => d[key] !== null && d[key] !== undefined)
        );

      const processedHasValidData = hasValidXAxis && hasValidYAxis;
      const isProcessed = useProcessedData && processedHasValidData;

      const source = isProcessed ? processedChartData : rawChartData;

      const sortedData = [...source].sort((a, b) => {
        const aVal = (a as any)[xKey];
        const bVal = (b as any)[xKey];
        if (typeof aVal === 'number' && typeof bVal === 'number') {
          return aVal - bVal;
        }
        return 0;
      });

      return { data: sortedData, isProcessed };
    },
    [processedChartData, rawChartData, useProcessedData]
  );

  const hasChartData = useMemo(() => {
    return useProcessedData ? processedChartData.length > 0 : rawChartData.length > 0;
  }, [processedChartData, rawChartData, useProcessedData]);

  // Pre-compute chart data for all 4 presets (avoids calling getChartDataForPreset per render)
  const presetChartDataMap = useMemo(() => {
    return QUAD_PRESETS.map(preset => ({
      key: preset.key,
      ...getChartDataForPreset(preset.x, preset.yLeft, preset.yRight),
    }));
  }, [getChartDataForPreset]);

  // ========== Persistence Functions ==========

  // Load saved config from server when test changes
  const loadSavedConfig = useCallback(async (testId: string) => {
    try {
      setPersistenceLoaded(false);
      const response = await api.getProcessedMetabolism(testId);

      // Apply server config to both serverConfig and local state
      const config = response.config;

      // IMPORTANT: serverConfig should only contain what's actually SAVED in DB
      // NOT auto-detected values from the analysis response
      const newServerConfig: ServerConfig = {
        loess: config.loess_frac,
        bin: config.bin_size,
        method: config.aggregation_method,
        minPower: config.min_power_threshold ?? 0,
        // Only include trim values if they were explicitly saved (is_persisted=true)
        // or if config explicitly has them set
        trimStart: config.trim_start_sec,
        trimEnd: config.trim_end_sec,
        vo2maxStart: config.vo2max_start_sec ?? null,
        vo2maxEnd: config.vo2max_end_sec ?? null,
      };

      setServerConfig(newServerConfig);
      setIsServerPersisted(response.is_persisted);

      // Apply to local state (analysis settings)
      setAnalysisSettings({
        loess: config.loess_frac,
        bin: config.bin_size,
        method: config.aggregation_method,
        minPower: config.min_power_threshold ?? 0,
      });

      // Apply trim range to local state
      // If config has explicit trim values, use them
      // Otherwise, use auto-detected from response (but don't save to serverConfig)
      if (config.trim_start_sec !== null && config.trim_end_sec !== null) {
        setTrimRange({
          start: config.trim_start_sec,
          end: config.trim_end_sec,
        });
      } else if (response.trim_range) {
        // Use auto-detected range from response for local state only
        // This allows user to see the auto-detected range but it's considered "dirty"
        // if they keep it (since serverConfig.trimStart/End are null)
        setTrimRange({
          start: response.trim_range.start_sec,
          end: response.trim_range.end_sec,
        });
      } else {
        // No trim range, set to null
        setTrimRange(null);
      }

      // v1.2.0: VO2max segment range
      if (config.vo2max_start_sec != null && config.vo2max_end_sec != null) {
        setVo2maxRange({
          start: config.vo2max_start_sec,
          end: config.vo2max_end_sec,
        });
      } else {
        setVo2maxRange(null);
      }

    } catch (error) {
      console.warn('[Persistence] Failed to load saved config, using defaults:', error);
      // Keep current defaults
    } finally {
      setPersistenceLoaded(true);
    }
  }, []);

  // Save current settings to server
  const handleSaveSettings = useCallback(async () => {
    if (!selectedTestId || isSaving) return;

    setIsSaving(true);
    try {
      const configToSave: MetabolismConfigApi = {
        bin_size: analysisSettings.bin,
        aggregation_method: analysisSettings.method,
        loess_frac: analysisSettings.loess,
        smoothing_method: 'loess',
        exclude_rest: true,
        exclude_warmup: true,
        exclude_recovery: true,
        min_power_threshold: analysisSettings.minPower === 0 ? null : analysisSettings.minPower,
        trim_start_sec: trimRange?.start ?? null,
        trim_end_sec: trimRange?.end ?? null,
        fatmax_zone_threshold: 0.90,
        vo2max_start_sec: vo2maxRange?.start ?? null,
        vo2max_end_sec: vo2maxRange?.end ?? null,
      };

      const response = await api.saveProcessedMetabolism(selectedTestId, configToSave, true);

      // Update server config to match what we just saved
      const newServerConfig: ServerConfig = {
        loess: response.config.loess_frac,
        bin: response.config.bin_size,
        method: response.config.aggregation_method,
        minPower: response.config.min_power_threshold ?? 0,
        trimStart: response.config.trim_start_sec,
        trimEnd: response.config.trim_end_sec,
        vo2maxStart: response.config.vo2max_start_sec ?? null,
        vo2maxEnd: response.config.vo2max_end_sec ?? null,
      };

      setServerConfig(newServerConfig);
      setIsServerPersisted(true);

      toast.success('분석 설정이 저장되었습니다.');

      // 저장 후 전처리 데이터 리로드 (결과 반영)
      if (dataMode === 'raw') {
        // Raw 모드에서 전처리 수행 시 Smooth 모드로 전환
        setDataMode('smoothed');
        // dataMode state 변경 후 useEffect에서 loadProcessedData가 호출됨
      } else {
        // 이미 Smooth/Trend 모드면 현재 모드로 리로드
        loadProcessedData(dataMode === 'trend' ? 'trend' : 'smoothed');
      }
    } catch (error: any) {
      console.error('[Persistence] Failed to save:', error);
      toast.error('설정 저장에 실패했습니다: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsSaving(false);
    }
  }, [selectedTestId, analysisSettings, trimRange, vo2maxRange, isSaving, dataMode]);

  // Reset to server defaults
  const handleResetSettings = useCallback(async () => {
    if (!selectedTestId || isResetting) return;

    setIsResetting(true);
    try {
      await api.deleteProcessedMetabolism(selectedTestId);

      // Reload default config from server
      const response = await api.getProcessedMetabolism(selectedTestId);

      const config = response.config;
      const newServerConfig: ServerConfig = {
        loess: config.loess_frac,
        bin: config.bin_size,
        method: config.aggregation_method,
        minPower: config.min_power_threshold ?? 0,
        trimStart: config.trim_start_sec,
        trimEnd: config.trim_end_sec,
        vo2maxStart: config.vo2max_start_sec ?? null,
        vo2maxEnd: config.vo2max_end_sec ?? null,
      };

      setServerConfig(newServerConfig);
      setIsServerPersisted(false);

      // Apply to local state
      setAnalysisSettings({
        loess: config.loess_frac,
        bin: config.bin_size,
        method: config.aggregation_method,
        minPower: config.min_power_threshold ?? 0,
      });

      // Reset trim range
      if (config.trim_start_sec !== null && config.trim_end_sec !== null) {
        setTrimRange({
          start: config.trim_start_sec,
          end: config.trim_end_sec,
        });
      } else {
        setTrimRange(null);
      }

      // Reset vo2max range
      if (config.vo2max_start_sec != null && config.vo2max_end_sec != null) {
        setVo2maxRange({
          start: config.vo2max_start_sec,
          end: config.vo2max_end_sec,
        });
      } else {
        setVo2maxRange(null);
      }

      toast.success('기본 설정으로 리셋되었습니다.');

      // Reload processed data with new settings
      if (useProcessedData) {
        loadProcessedData();
      }
    } catch (error: any) {
      console.error('[Persistence] Failed to reset:', error);
      toast.error('리셋에 실패했습니다: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsResetting(false);
    }
  }, [selectedTestId, isResetting, useProcessedData]);

  // 피험자 목록 로드
  useEffect(() => {
    loadSubjects();
  }, []);

  async function loadSubjects() {
    try {
      setLoadingSubjects(true);
      const token = getAuthToken();
      const response = await fetch(`${API_BASE}/subjects?page_size=100`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load subjects');
      const data = await response.json();

      const options: SubjectOption[] = data.items.map((s: any) => ({
        id: s.id,
        name: s.encrypted_name || s.name || s.research_id,
        research_id: s.research_id,
      }));
      setSubjects(options);

      // 테스트 목록도 같이 로드
      await loadAllTests();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoadingSubjects(false);
    }
  }

  // 전체 테스트 목록 로드
  async function loadAllTests() {
    try {
      setLoadingTests(true);
      const token = getAuthToken();
      const response = await fetch(`${API_BASE}/tests?page_size=100`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load tests');
      const data = await response.json();

      const options: TestOption[] = data.items.map((t: any) => {
        // subjects에서 subject_name 찾기
        const subject = subjects.find(s => s.id === t.subject_id);
        return {
          test_id: t.test_id,
          source_filename: t.source_filename || 'Unknown',
          test_date: t.test_date,
          subject_id: t.subject_id,
          subject_name: subject?.name || subject?.research_id || 'Unknown',
          protocol_type: t.protocol_type,
          is_valid: t.is_valid,
        };
      });
      setTests(options);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoadingTests(false);
    }
  }

  // 피험자 선택 시 해당 피험자의 테스트만 필터
  useEffect(() => {
    if (selectedSubjectId) {
      // UUID 문자열 비교 (대소문자 무시)
      const filtered = tests.filter(t =>
        String(t.subject_id).toLowerCase() === String(selectedSubjectId).toLowerCase()
      );
      setFilteredTests(filtered);
      setSelectedTestId('');
      setRawData(null);
      setProcessedData(null);
      setAnalysisData(null);
      setVo2maxRange(null);
    } else {
      setFilteredTests([]);
      setSelectedTestId('');
      setRawData(null);
      setProcessedData(null);
      setAnalysisData(null);
      setVo2maxRange(null);
    }
  }, [selectedSubjectId, tests]);

  // 테스트 선택 시 저장된 설정 먼저 로드
  useEffect(() => {
    if (selectedTestId) {
      loadSavedConfig(selectedTestId);
    }
  }, [selectedTestId, loadSavedConfig]);

  // 테스트 선택 시 자동으로 데이터 로드
  useEffect(() => {
    if (selectedTestId && !useProcessedData) {
      loadRawData();
    }
  }, [selectedTestId, useProcessedData]);

  useEffect(() => {
    if (selectedTestId && useProcessedData) {
      loadProcessedData();
    }
  }, [selectedTestId, useProcessedData, dataMode, debouncedLoess, debouncedBin, debouncedMinPower, analysisSettings.method, debouncedTrimRange, debouncedVo2maxRange]);

  // 선택한 테스트의 raw data 로드
  async function loadRawData() {
    if (!selectedTestId) return;

    try {
      setLoading(true);
      const token = getAuthToken();
      const response = await fetch(`${API_BASE}/tests/${selectedTestId}/raw-data`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to load raw data');
      }
      const data: RawDataResponse = await response.json();
      setRawData(data);
      setCurrentPage(1);
    } catch (error) {
      toast.error(getErrorMessage(error));
      setRawData(null);
    } finally {
      setLoading(false);
    }
  }

  // 전처리된 데이터 로드 (TestAnalysis API 사용)
  async function loadProcessedData(overrideMode?: 'smoothed' | 'trend') {
    if (!selectedTestId) return;

    // 명시적으로 전달된 mode를 우선 사용, 없으면 현재 state 사용
    const currentMode = overrideMode || dataMode;

    try {
      setLoading(true);
      const token = getAuthToken();
      // Build query params including trim range if set
      const params = new URLSearchParams({
        interval: '5s',
        include_processed: 'true',
        loess_frac: String(debouncedLoess),
        bin_size: String(debouncedBin),
        aggregation_method: analysisSettings.method,
        min_power_threshold: String(debouncedMinPower),
      });
      // Add trim params if manually adjusted
      if (debouncedTrimRange) {
        params.set('trim_start_sec', String(debouncedTrimRange.start));
        params.set('trim_end_sec', String(debouncedTrimRange.end));
      }
      // v1.2.0: VO2max segment params
      if (debouncedVo2maxRange) {
        params.set('vo2max_start_sec', String(debouncedVo2maxRange.start));
        params.set('vo2max_end_sec', String(debouncedVo2maxRange.end));
      }
      const response = await fetch(
        `${API_BASE}/tests/${selectedTestId}/analysis?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to load processed data');
      }
      const data = await response.json();

      // Update trim range from API response (auto-detected value)
      // Always update if not manually set (trimRange === null), otherwise keep user's manual setting
      if (data.used_trim_range) {
        // Only set auto-detected range if user hasn't manually adjusted
        if (trimRange === null) {
          setTrimRange({
            start: data.used_trim_range.start_sec,
            end: data.used_trim_range.end_sec,
          });
        }
      }
      // Update total duration for slider max
      if (data.total_duration_sec) {
        setTotalDuration(data.total_duration_sec);
      }

      setAnalysisData(data);

      // currentMode에 따라 적절한 데이터 소스 선택
      const sourceKey = currentMode === 'trend' ? 'trend' : 'smoothed';
      const sourceData = data.processed_series?.[sourceKey] || data.processed_series?.smoothed;

      if (sourceData && sourceData.length > 0) {

        // Trend 모드일 경우 배경에 그릴 Smooth 데이터 준비
        const smoothData = data.processed_series?.smoothed || [];

        // Build a Map for O(1) smooth data lookup by rounded power (instead of O(n) per point)
        const smoothMap = new Map<number, any>();
        if (currentMode === 'trend' && smoothData.length > 0) {
          for (const s of smoothData) {
            smoothMap.set(Math.round(s.power), s);
          }
        }

        const safeVal = (v: any) => (v !== null && v !== undefined ? v : null);

        const chartDataPoints = sourceData.map((point: any) => {
          const base: any = {
            bike_power: point.power ?? 0,
            power: point.power ?? 0,
            fat_oxidation: safeVal(point.fat_oxidation),
            cho_oxidation: safeVal(point.cho_oxidation),
            rer: safeVal(point.rer),
            vo2: safeVal(point.vo2),
            vco2: safeVal(point.vco2),
            vo2_rel: safeVal(point.vo2_rel),
            hr: safeVal(point.hr),
            ve_vo2: safeVal(point.ve_vo2),
            ve_vco2: safeVal(point.ve_vco2),
            total_oxidation: (point.fat_oxidation ?? 0) + (point.cho_oxidation ?? 0),
          };

          // Trend 모드: O(1) Map lookup for nearest smooth data
          if (currentMode === 'trend' && smoothMap.size > 0) {
            const roundedPower = Math.round(point.power);
            const nearestSmooth = smoothMap.get(roundedPower);

            if (nearestSmooth) {
              base.fat_oxidation_smooth = safeVal(nearestSmooth.fat_oxidation);
              base.cho_oxidation_smooth = safeVal(nearestSmooth.cho_oxidation);
              base.rer_smooth = safeVal(nearestSmooth.rer);
              base.vo2_smooth = safeVal(nearestSmooth.vo2);
              base.vco2_smooth = safeVal(nearestSmooth.vco2);
              base.vo2_rel_smooth = safeVal(nearestSmooth.vo2_rel);
              base.hr_smooth = safeVal(nearestSmooth.hr);
              base.ve_vo2_smooth = safeVal(nearestSmooth.ve_vo2);
              base.ve_vco2_smooth = safeVal(nearestSmooth.ve_vco2);
            }
          }

          return base;
        });

        setProcessedData({
          data: chartDataPoints,
          // 모든 시리즈 저장 (차트 오버레이용)
          allSeries: {
            raw: data.processed_series?.raw || [],
            binned: data.processed_series?.binned || [],
            smoothed: data.processed_series?.smoothed || [],
            trend: data.processed_series?.trend || [],
          }
        });
        setShowChart(true);
      } else {
        if (currentMode === 'trend' && !data.processed_series?.trend) {
          toast.warning('Trend 데이터가 없습니다. Smooth 모드를 사용하세요.');
        } else {
          toast.warning('전처리 데이터가 없습니다. Raw 데이터를 확인하세요.');
        }
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
      setProcessedData(null);
      setAnalysisData(null);
    } finally {
      setLoading(false);
    }
  }

  // 페이지네이션
  const totalPages = rawData ? Math.ceil(rawData.data.length / PAGE_SIZE) : 0;
  const paginatedData = rawData
    ? rawData.data.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
    : [];

  // CSV 다운로드
  function downloadCSV() {
    if (!rawData) return;

    const headers = displayColumns.map(c => c.label).join(',');
    const rows = rawData.data.map(row =>
      displayColumns.map(col => {
        const value = (row as any)[col.key];
        return value ?? '';
      }).join(',')
    );

    const csv = [headers, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${rawData.source_filename || 'raw_data'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('CSV 다운로드 완료 (선택된 컬럼만)');
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="raw-data" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-full mx-auto px-3 sm:px-4 md:px-6 pt-4 md:pt-6">
        {/* 필터 영역 - 피험자 & 테스트 날짜 선택 */}
        <div className="bg-white border border-gray-200 rounded-lg p-3 sm:p-4 mb-4 shadow-sm">
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center sm:flex-wrap">
            {/* 피험자 선택 */}
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-gray-500" />
              <label className="text-sm font-medium text-gray-700">피험자</label>
              <select
                className="px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2563EB] text-sm w-full sm:w-auto sm:min-w-[180px]"
                value={selectedSubjectId}
                onChange={(e) => setSelectedSubjectId(e.target.value)}
                disabled={loadingSubjects}
              >
                <option value="">피험자 선택...</option>
                {loadingSubjects ? (
                  <option disabled>로딩중...</option>
                ) : subjects.length === 0 ? (
                  <option disabled>등록된 피험자 없음</option>
                ) : (
                  subjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.research_id})
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* 테스트 날짜 선택 */}
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-500" />
              <label className="text-sm font-medium text-gray-700">테스트</label>
              <select
                className="px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2563EB] text-sm w-full sm:w-auto sm:min-w-[200px] md:min-w-[280px] disabled:bg-gray-100"
                value={selectedTestId}
                onChange={(e) => setSelectedTestId(e.target.value)}
                disabled={!selectedSubjectId || loadingTests}
              >
                {!selectedSubjectId ? (
                  <option value="">피험자를 먼저 선택하세요</option>
                ) : filteredTests.length === 0 ? (
                  <option value="">테스트 없음</option>
                ) : (
                  <>
                    <option value="">테스트 선택...</option>
                    {filteredTests.map((t) => {
                      const protocolLabel = t.protocol_type || 'MIX';
                      const validLabel = t.is_valid === true ? '✓유효' : t.is_valid === false ? '✗무효' : '-';
                      const dateStr = new Date(t.test_date).toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' });
                      return (
                        <option key={t.test_id} value={t.test_id}>
                          {dateStr} | {protocolLabel} | {validLabel}
                        </option>
                      );
                    })}
                  </>
                )}
              </select>
            </div>

            {/* 3-Way 데이터 모드 토글 */}
            <div className="flex items-center gap-2 sm:border-l sm:pl-4 pt-2 sm:pt-0 border-t sm:border-t-0">
              <label className="text-sm font-medium text-gray-700">데이터 표시:</label>
              <div className="inline-flex rounded-md shadow-sm" role="group">
                <button
                  type="button"
                  onClick={() => {
                    setDataMode('raw');
                    if (selectedTestId) loadRawData();
                  }}
                  disabled={!selectedTestId}
                  className={`px-3 py-1.5 text-sm font-medium border ${dataMode === 'raw'
                    ? 'bg-blue-600 text-white border-blue-600 z-10'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    } rounded-l-md focus:z-10 focus:ring-2 focus:ring-blue-500 disabled:opacity-50`}
                >
                  Raw
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDataMode('smoothed');
                    if (selectedTestId) loadProcessedData('smoothed');
                  }}
                  disabled={!selectedTestId}
                  className={`px-3 py-1.5 text-sm font-medium border-t border-b ${dataMode === 'smoothed'
                    ? 'bg-blue-600 text-white border-blue-600 z-10'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    } focus:z-10 focus:ring-2 focus:ring-blue-500 disabled:opacity-50`}
                >
                  Smooth
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDataMode('trend');
                    if (selectedTestId) loadProcessedData('trend');
                  }}
                  disabled={!selectedTestId}
                  className={`px-3 py-1.5 text-sm font-medium border ${dataMode === 'trend'
                    ? 'bg-blue-600 text-white border-blue-600 z-10'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    } rounded-r-md focus:z-10 focus:ring-2 focus:ring-blue-500 disabled:opacity-50`}
                >
                  Trend
                </button>
              </div>

              {/* 전처리 수행 버튼 */}
              <button
                type="button"
                onClick={handleSaveSettings}
                disabled={!selectedTestId || isSaving}
                className={`ml-2 px-3 py-1.5 text-sm font-medium rounded-md shadow-sm inline-flex items-center gap-1.5
                  ${isSaving
                    ? 'bg-gray-400 text-white cursor-wait'
                    : isDirty
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : 'bg-gray-300 text-gray-600 hover:bg-gray-400'
                  }
                  focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-50 transition-colors`}
                title={isDirty ? "현재 설정으로 전처리 수행 및 저장" : "이미 저장됨"}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    저장 중...
                  </>
                ) : isDirty ? (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    전처리 수행
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    저장됨
                  </>
                )}
              </button>

              {/* 리셋 버튼 */}
              {selectedTestId && isServerPersisted && (
                <button
                  type="button"
                  onClick={handleResetSettings}
                  disabled={isResetting}
                  className="px-2 py-1.5 text-sm font-medium rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:opacity-50 transition-colors inline-flex items-center gap-1"
                  title="기본 설정으로 리셋"
                >
                  {isResetting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="w-3.5 h-3.5" />
                  )}
                </button>
              )}
            </div>

            {/* 전처리 파라미터 컨트롤 */}
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex flex-col gap-1 min-w-[140px]">
                <label className={`text-xs font-medium ${useProcessedData ? 'text-gray-700' : 'text-gray-400'}`}>
                  LOESS 강도 ({analysisSettings.loess.toFixed(2)})
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={0.5}
                  step={0.05}
                  value={analysisSettings.loess}
                  onChange={(e) => setAnalysisSettings(prev => ({ ...prev, loess: parseFloat(e.target.value) }))}
                  disabled={!useProcessedData}
                  className="w-full"
                />
              </div>
              <div className="flex flex-col gap-1 min-w-[140px]">
                <label className={`text-xs font-medium ${useProcessedData ? 'text-gray-700' : 'text-gray-400'}`}>
                  Power Bin ({analysisSettings.bin}W)
                </label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  step={5}
                  value={analysisSettings.bin}
                  onChange={(e) => setAnalysisSettings(prev => ({ ...prev, bin: parseInt(e.target.value, 10) }))}
                  disabled={!useProcessedData}
                  className="w-full"
                />
              </div>
              <div className="flex flex-col gap-1 min-w-[140px]">
                <label className={`text-xs font-medium ${useProcessedData ? 'text-gray-700' : 'text-gray-400'}`}>
                  Min Power ({analysisSettings.minPower}W)
                </label>
                <input
                  type="range"
                  min={0}
                  max={200}
                  step={10}
                  value={analysisSettings.minPower}
                  onChange={(e) => setAnalysisSettings(prev => ({ ...prev, minPower: parseInt(e.target.value, 10) }))}
                  disabled={!useProcessedData}
                  className="w-full"
                />
              </div>
              <div className="flex flex-col gap-1 min-w-[120px]">
                <label className={`text-xs font-medium ${useProcessedData ? 'text-gray-700' : 'text-gray-400'}`}>
                  집계 방식
                </label>
                <select
                  className="px-2 py-1 border border-gray-300 rounded-md text-xs"
                  value={analysisSettings.method}
                  onChange={(e) => setAnalysisSettings(prev => ({ ...prev, method: e.target.value as 'median' | 'mean' | 'trimmed_mean' }))}
                  disabled={!useProcessedData}
                >
                  <option value="median">Median</option>
                  <option value="mean">Mean</option>
                  <option value="trimmed_mean">Trimmed Mean</option>
                </select>
              </div>
            </div>

            {/* Dual Segment Sliders (FATMAX + VO2max) */}
            {useProcessedData && (
              <div className="flex flex-col gap-2 py-2 px-3 bg-gray-50 rounded-lg border border-gray-200 w-full">
                {/* FATMAX Segment Slider */}
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5 min-w-[110px]">
                    <Scissors className="w-4 h-4 text-blue-500" />
                    <span className="text-xs font-medium text-blue-700">FATMAX 구간</span>
                  </div>
                  <div className="flex-1 min-w-[200px]">
                    <Slider
                      min={0}
                      max={totalDuration}
                      step={5}
                      value={trimRange ? [trimRange.start, trimRange.end] : [0, totalDuration]}
                      onValueChange={(values) => {
                        setTrimRange({ start: values[0], end: values[1] });
                      }}
                      className="w-full"
                    />
                  </div>
                  <div className="text-xs text-gray-600 min-w-[120px] text-right">
                    {trimRange ? (
                      <>
                        {Math.round(trimRange.start)}s - {Math.round(trimRange.end)}s
                        <span className="ml-1.5 text-gray-400">
                          ({Math.round(trimRange.end - trimRange.start)}s)
                        </span>
                      </>
                    ) : (
                      <span className="text-gray-400">Auto-detect</span>
                    )}
                  </div>
                  {trimRange && (
                    <button
                      onClick={() => setTrimRange(null)}
                      className="p-1 hover:bg-gray-200 rounded text-gray-400 hover:text-gray-600"
                      title="Reset to auto-detect"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                {/* VO2max Segment Slider */}
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5 min-w-[110px]">
                    <Scissors className="w-4 h-4 text-orange-500" />
                    <span className="text-xs font-medium text-orange-700">VO2max 구간</span>
                  </div>
                  <div className="flex-1 min-w-[200px]">
                    <Slider
                      min={0}
                      max={totalDuration}
                      step={5}
                      value={vo2maxRange ? [vo2maxRange.start, vo2maxRange.end] : [0, totalDuration]}
                      onValueChange={(values) => {
                        setVo2maxRange({ start: values[0], end: values[1] });
                      }}
                      className="w-full"
                    />
                  </div>
                  <div className="text-xs text-gray-600 min-w-[120px] text-right">
                    {vo2maxRange ? (
                      <>
                        {Math.round(vo2maxRange.start)}s - {Math.round(vo2maxRange.end)}s
                        <span className="ml-1.5 text-gray-400">
                          ({Math.round(vo2maxRange.end - vo2maxRange.start)}s)
                        </span>
                      </>
                    ) : (
                      <span className="text-gray-400">Not set</span>
                    )}
                  </div>
                  {vo2maxRange && (
                    <button
                      onClick={() => setVo2maxRange(null)}
                      className="p-1 hover:bg-gray-200 rounded text-gray-400 hover:text-gray-600"
                      title="Clear VO2max segment"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* CSV 다운로드 */}
            <Button variant="outline" size="sm" onClick={downloadCSV} disabled={!rawData && !processedData} className="ml-auto">
              <Download className="w-4 h-4 mr-1" />
              CSV
            </Button>
          </div>

          {/* 선택된 정보 표시 */}
          {(rawData || processedData) && (
            <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-4 text-sm text-gray-600 flex-wrap">
              {rawData && !useProcessedData && (
                <>
                  <span className="font-medium text-gray-900">{rawData.source_filename}</span>
                  <span>피험자: {rawData.subject_name || 'Unknown'}</span>
                  <span>날짜: {new Date(rawData.test_date).toLocaleDateString()}</span>
                  <span>총 {rawData.total_rows.toLocaleString()}행</span>
                  <span>표시 컬럼: {displayColumns.length}개</span>
                </>
              )}
              {processedData && useProcessedData && (
                <>
                  <span className={`font-medium ${dataMode === 'trend' ? 'text-purple-700' : 'text-teal-700'}`}>
                    {dataMode === 'trend'
                      ? '📈 Polynomial Trend (2차 전처리)'
                      : '✨ LOESS Smoothed (1차 전처리)'}
                  </span>
                  <span>데이터 포인트: {processedData.data?.length || 0}개</span>
                  {analysisData?.metabolic_markers?.fat_max && (
                    <span className="text-orange-600">FatMax: {analysisData.metabolic_markers.fat_max.power}W</span>
                  )}
                  {analysisData?.metabolic_markers?.crossover?.power && (
                    <span className="text-purple-600">Crossover: {analysisData.metabolic_markers.crossover.power}W</span>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* 차트 영역 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : (rawData || processedData) && showChart ? (
          <Card className="mb-4">
            <CardHeader className="py-3">
              <div className="flex justify-between items-center">
                <CardTitle className="text-base flex items-center gap-2">
                  <LineChart className="w-4 h-4" />
                  데이터 차트 (4분할)
                </CardTitle>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">FATMAX · RER · VO2 · VT</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowChart(false)}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {!hasChartData ? (
                <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                  <div className="text-center text-gray-500">
                    <LineChart className="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p className="font-medium">차트 데이터를 불러오는 중입니다</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-lg border border-gray-200 bg-white p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-gray-700">테스트 개요 (시간 vs HR/Power)</span>
                      <span className="text-[11px] text-gray-400">X: Time(s)</span>
                    </div>
                    <div className="h-44 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={rawChartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }} syncId="rawDataViewer">
                          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                          <XAxis
                            dataKey="t_sec"
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            tick={{ fontSize: 10 }}
                            tickFormatter={numberTickFormatter}
                          />
                          <YAxis
                            yAxisId="left"
                            type="number"
                            domain={['auto', 'auto']}
                            tick={{ fontSize: 10 }}
                            tickFormatter={numberTickFormatter}
                          />
                          <YAxis
                            yAxisId="right"
                            orientation="right"
                            type="number"
                            domain={['auto', 'auto']}
                            tick={{ fontSize: 10 }}
                            tickFormatter={numberTickFormatter}
                          />
                          <Tooltip
                            contentStyle={{ fontSize: 11 }}
                            formatter={overviewTooltipFormatter}
                            labelFormatter={overviewLabelFormatter}
                          />
                          {/* FATMAX segment overlay (blue) */}
                          {trimRange && (
                            <ReferenceArea
                              x1={trimRange.start}
                              x2={trimRange.end}
                              yAxisId="left"
                              fill="#3B82F6"
                              fillOpacity={0.08}
                              stroke="#3B82F6"
                              strokeOpacity={0.3}
                              strokeDasharray="3 3"
                              label={{ value: "FATMAX", position: "insideTopLeft", fontSize: 10, fill: "#3B82F6" }}
                            />
                          )}
                          {/* VO2max segment overlay (orange) */}
                          {vo2maxRange && (
                            <ReferenceArea
                              x1={vo2maxRange.start}
                              x2={vo2maxRange.end}
                              yAxisId="left"
                              fill="#F97316"
                              fillOpacity={0.08}
                              stroke="#F97316"
                              strokeOpacity={0.3}
                              strokeDasharray="3 3"
                              label={{ value: "VO2max", position: "insideTopLeft", fontSize: 10, fill: "#F97316" }}
                            />
                          )}
                          <Line
                            yAxisId="left"
                            type="monotone"
                            dataKey="hr"
                            name="HR"
                            stroke="#2563EB"
                            strokeWidth={2}
                            dot={false}
                          />
                          <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey="bike_power"
                            name="Power"
                            stroke="#DC2626"
                            strokeWidth={2}
                            dot={false}
                          />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {QUAD_PRESETS.map((preset, presetIndex) => (
                      <PresetChart
                        key={preset.key}
                        preset={preset}
                        presetIndex={presetIndex}
                        chartData={presetChartDataMap[presetIndex].data}
                        isProcessed={presetChartDataMap[presetIndex].isProcessed}
                        dataMode={dataMode}
                        analysisData={analysisData}
                      />
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (rawData || processedData) && !showChart ? (
          <div className="mb-4">
            <Button variant="outline" size="sm" onClick={() => setShowChart(true)}>
              <LineChart className="w-4 h-4 mr-1" />
              차트 표시
            </Button>
          </div>
        ) : null}

        {/* 데이터 테이블 */}
        {!loading && rawData ? (
          <Card>
            <CardHeader className="py-3">
              <div className="flex justify-between items-center">
                <CardTitle className="text-base flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  Breath Data
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowRawTable((prev) => !prev)}
                  >
                    {showRawTable ? '표 숨기기' : '표 보기'}
                  </Button>
                  {showRawTable && (
                    <>
                      {/* 컬럼 선택기 */}
                      <div className="relative" ref={columnSelectorRef}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowColumnSelector(!showColumnSelector)}
                          className="gap-1"
                        >
                          <Settings2 className="w-4 h-4" />
                          컬럼 선택
                        </Button>

                        {showColumnSelector && (
                          <div className="absolute right-0 top-full mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                            <div className="p-3 border-b bg-gray-50">
                              <div className="flex justify-between items-center">
                                <span className="font-medium text-sm">표시할 컬럼 선택</span>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setSelectedColumns(DEFAULT_SELECTED_COLUMNS)}
                                  className="text-xs h-6 px-2"
                                >
                                  기본값
                                </Button>
                              </div>
                            </div>

                            {(Object.keys(COLUMN_GROUPS) as Array<keyof typeof COLUMN_GROUPS>).map(group => {
                              const groupColumns = SELECTABLE_COLUMNS.filter(c => c.group === group);
                              const allSelected = groupColumns.every(c => selectedColumns.includes(c.key));
                              const someSelected = groupColumns.some(c => selectedColumns.includes(c.key));

                              return (
                                <div key={group} className="border-b last:border-b-0">
                                  <div
                                    className="flex items-center gap-2 p-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
                                    onClick={() => toggleGroup(group)}
                                  >
                                    <div className={`w-4 h-4 rounded border flex items-center justify-center ${allSelected ? 'bg-[#2563EB] border-[#2563EB]' :
                                      someSelected ? 'bg-[#2563EB]/50 border-[#2563EB]' : 'border-gray-300'
                                      }`}>
                                      {allSelected && <Check className="w-3 h-3 text-white" />}
                                    </div>
                                    <span className={`px-2 py-0.5 text-xs rounded ${COLUMN_GROUPS[group].color}`}>
                                      {COLUMN_GROUPS[group].label}
                                    </span>
                                    <span className="text-xs text-gray-500">
                                      ({groupColumns.filter(c => selectedColumns.includes(c.key)).length}/{groupColumns.length})
                                    </span>
                                  </div>
                                  <div className="px-3 py-2 grid grid-cols-2 gap-1">
                                    {groupColumns.map(col => (
                                      <label
                                        key={col.key}
                                        className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-50 cursor-pointer text-sm"
                                      >
                                        <input
                                          type="checkbox"
                                          checked={selectedColumns.includes(col.key)}
                                          onChange={() => toggleColumn(col.key)}
                                          className="w-3.5 h-3.5 rounded border-gray-300 text-[#2563EB] focus:ring-[#2563EB]"
                                        />
                                        {col.label}
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      <div className="w-px h-6 bg-gray-300" />

                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </Button>
                      <span className="text-sm text-gray-600">
                        {currentPage} / {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            {showRawTable && (
              <CardContent className="p-0">
                {/* 고정 컬럼 + 스크롤 가능 테이블 */}
                <div className="flex">
                  {/* 왼쪽 고정 컬럼 (#, Time, Phase) */}
                  <div className="flex-shrink-0 border-r border-gray-200 bg-white z-10 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.1)]">
                    <table className="text-sm">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">#</th>
                          {FIXED_COLUMNS.map(col => (
                            <th key={col.key} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">
                              {col.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedData.map((row, idx) => (
                          <tr key={row.id} className="border-b hover:bg-gray-50">
                            <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap">
                              {(currentPage - 1) * PAGE_SIZE + idx + 1}
                            </td>
                            {FIXED_COLUMNS.map(col => (
                              <td key={col.key} className="px-3 py-1.5 text-gray-900 font-mono text-xs whitespace-nowrap">
                                {col.format((row as any)[col.key])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* 오른쪽 스크롤 가능 영역 */}
                  <div className="overflow-x-auto flex-1">
                    <table className="text-sm w-full">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          {SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key)).map(col => (
                            <th key={col.key} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">
                              <span className="flex items-center gap-1">
                                {col.label}
                                <span className={`w-2 h-2 rounded-full ${col.group === 'basic' ? 'bg-blue-400' :
                                  col.group === 'respiratory' ? 'bg-green-400' :
                                    col.group === 'metabolic' ? 'bg-orange-400' :
                                      'bg-purple-400'
                                  }`} title={COLUMN_GROUPS[col.group as keyof typeof COLUMN_GROUPS].label} />
                              </span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedData.map((row) => (
                          <tr key={row.id} className="border-b hover:bg-gray-50">
                            {SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key)).map(col => (
                              <td key={col.key} className="px-3 py-1.5 text-gray-900 font-mono text-xs whitespace-nowrap">
                                {col.format((row as any)[col.key])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>
        ) : null}

        {/* 빈 상태 표시 */}
        {!loading && !rawData && (
          <Card className="p-12 text-center text-gray-400">
            <Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-lg font-medium text-gray-500">피험자와 테스트를 선택하세요</p>
            <p className="text-sm mt-1">상단 필터에서 피험자를 먼저 선택한 후, 테스트 날짜를 선택하면 데이터가 표시됩니다.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
