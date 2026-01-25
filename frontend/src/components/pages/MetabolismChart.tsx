import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Label,
  ComposedChart,
} from 'recharts';
import type { ProcessedSeries, MetabolicMarkers } from '@/lib/api';

export type DataMode = 'raw' | 'smoothed' | 'trend';

// 데이터 키별 고정 색상 (교수님 차트 기준)
const DATA_COLORS = {
  fat: '#DC2626',      // 빨강 (Fat)
  cho: '#16A34A',      // 녹색 (CHO)
  vo2_rel: '#2563EB',  // 파랑 (VO2/kg)
};

interface MetabolismChartProps {
  data: Array<{
    power: number;
    fatOxidation: number;
    choOxidation: number;
    totalCalories: number;
  }>;
  fatMaxPower: number;
  duration?: string;
  tss?: number;
  title?: string;
  subjectName?: string;
  // New props for enhanced visualization
  processedSeries?: ProcessedSeries;
  markers?: MetabolicMarkers;
  dataMode?: DataMode;
  showRawOverlay?: boolean;
}

export function MetabolismChart({
  data,
  fatMaxPower,
  duration = "2:06",
  tss = 89,
  title = "FATMAX",
  subjectName,
  processedSeries,
  markers,
  dataMode = 'smoothed',
  showRawOverlay = false
}: MetabolismChartProps) {

  // Get FatMax zone from markers or use default
  const fatMaxZoneMin = markers?.fat_max?.zone_min ?? fatMaxPower - 20;
  const fatMaxZoneMax = markers?.fat_max?.zone_max ?? fatMaxPower + 20;
  const mfo = markers?.fat_max?.mfo;

  // Get Crossover point from markers
  const crossoverPower = markers?.crossover?.power;

  // Transform processed series data based on dataMode - g/min 단위 그대로 사용
  const getChartData = () => {
    if (!processedSeries) {
      // Legacy data - convert back from kcal/day to g/min
      return data.map(d => ({
        power: d.power,
        fat: d.fatOxidation / (9.75 * 60 * 24),
        cho: d.choOxidation / (4.07 * 60 * 24),
        vo2_rel: null,
      }));
    }

    let sourceData: Array<{ power: number; fat_oxidation: number | null; cho_oxidation: number | null; vo2_rel?: number | null }>;
    let smoothData: Array<{ power: number; fat_oxidation: number | null; cho_oxidation: number | null; vo2_rel?: number | null }> | null = null;

    switch (dataMode) {
      case 'raw':
        sourceData = processedSeries.binned;
        break;
      case 'trend':
        sourceData = processedSeries.trend || processedSeries.smoothed;
        smoothData = processedSeries.smoothed; // Background smooth line
        break;
      case 'smoothed':
      default:
        sourceData = processedSeries.smoothed;
        break;
    }

    return sourceData.map(point => {
      const baseData: any = {
        power: point.power,
        fat: point.fat_oxidation,
        cho: point.cho_oxidation,
        vo2_rel: (point as any).vo2_rel ?? null,
      };

      // Trend 모드일 때 배경 smooth 데이터 추가
      if (dataMode === 'trend' && smoothData) {
        const nearestSmooth = smoothData.reduce((prev, curr) =>
          Math.abs(curr.power - point.power) < Math.abs(prev.power - point.power) ? curr : prev
        );
        if (Math.abs(nearestSmooth.power - point.power) < 5) {
          baseData.fat_smooth = nearestSmooth.fat_oxidation;
          baseData.cho_smooth = nearestSmooth.cho_oxidation;
          baseData.vo2_rel_smooth = (nearestSmooth as any).vo2_rel ?? null;
        }
      }

      return baseData;
    }).filter(d => d.power >= 50).sort((a, b) => a.power - b.power);
  };

  const chartData = getChartData();

  // Calculate domains
  const maxFatCho = Math.max(
    ...chartData.map(d => Math.max(d.fat || 0, d.cho || 0)),
    1
  );
  const maxVo2Rel = Math.max(
    ...chartData.filter(d => d.vo2_rel !== null).map(d => d.vo2_rel || 0),
    60
  );
  const minPower = Math.min(...chartData.map(d => d.power));
  const maxPower = Math.max(...chartData.map(d => d.power));

  // Round up for nice axis
  const yLeftMax = Math.ceil(maxFatCho * 1.2 * 2) / 2; // Round to 0.5
  const yRightMax = Math.ceil(maxVo2Rel * 1.2 / 10) * 10; // Round to 10

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">{title}</h2>
          {subjectName && (
            <p className="text-sm text-gray-600">{subjectName}</p>
          )}
          {processedSeries && (
            <p className="text-xs text-gray-500">
              Data: {dataMode === 'smoothed' ? 'LOESS Smoothed' : dataMode === 'trend' ? 'Polynomial Trend' : 'Binned'}
            </p>
          )}
        </div>
        <span className="text-sm text-gray-400">X: Power</span>
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={chartData}
          margin={{ top: 20, right: 60, left: 20, bottom: 40 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />

          {/* X축 - Power (W) */}
          <XAxis
            dataKey="power"
            type="number"
            domain={[Math.floor(minPower / 10) * 10, Math.ceil(maxPower / 10) * 10]}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={(v) => v.toFixed(0)}
          >
            <Label value="W" position="insideBottomRight" offset={-5} style={{ fontSize: 11, fill: '#6b7280' }} />
          </XAxis>

          {/* Y축 왼쪽 - g/min (Fat, CHO) */}
          <YAxis
            yAxisId="left"
            domain={[0, yLeftMax]}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={(v) => v.toFixed(2)}
          >
            <Label
              value="g/min"
              angle={-90}
              position="insideLeft"
              style={{ fontSize: 11, fill: '#6b7280' }}
            />
          </YAxis>

          {/* Y축 오른쪽 - ml/min/kg (VO2/kg) */}
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, yRightMax]}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={(v) => v.toFixed(0)}
          >
            <Label
              value="ml/min/kg"
              angle={90}
              position="insideRight"
              style={{ fontSize: 11, fill: '#6b7280' }}
            />
          </YAxis>

          {/* Tooltip */}
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={(value: any, name: string) => {
              if (value === null || value === undefined) return ['—', name];
              const label = name === 'fat' ? 'Fat' : name === 'cho' ? 'CHO' : name === 'vo2_rel' ? 'VO2/kg' : name;
              const unit = name === 'vo2_rel' ? 'ml/min/kg' : 'g/min';
              return [`${Number(value).toFixed(2)} ${unit}`, label];
            }}
            labelFormatter={(label) => `Power: ${label}W`}
          />

          {/* FatMax Zone (Background highlight) */}
          <ReferenceArea
            x1={fatMaxZoneMin}
            x2={fatMaxZoneMax}
            yAxisId="left"
            fill="#3B82F6"
            fillOpacity={0.1}
            stroke="#3B82F6"
            strokeOpacity={0.3}
            strokeDasharray="3 3"
          />

          {/* Trend 모드일 때 배경 Smooth 라인 (흐리고 점선) */}
          {dataMode === 'trend' && (
            <>
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="fat_smooth"
                stroke={DATA_COLORS.fat}
                strokeWidth={1.5}
                strokeOpacity={0.3}
                strokeDasharray="6 4"
                dot={false}
                connectNulls
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="cho_smooth"
                stroke={DATA_COLORS.cho}
                strokeWidth={1.5}
                strokeOpacity={0.3}
                strokeDasharray="6 4"
                dot={false}
                connectNulls
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="vo2_rel_smooth"
                stroke={DATA_COLORS.vo2_rel}
                strokeWidth={1.5}
                strokeOpacity={0.3}
                strokeDasharray="6 4"
                dot={false}
                connectNulls
              />
            </>
          )}

          {/* Fat oxidation - 빨강 */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="fat"
            name="Fat"
            stroke={DATA_COLORS.fat}
            strokeWidth={dataMode === 'trend' ? 3.5 : 2.5}
            dot={false}
            connectNulls
          />

          {/* CHO oxidation - 녹색 */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="cho"
            name="CHO"
            stroke={DATA_COLORS.cho}
            strokeWidth={dataMode === 'trend' ? 3.5 : 2.5}
            dot={false}
            connectNulls
          />

          {/* VO2/kg - 파랑 */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="vo2_rel"
            name="VO2/kg"
            stroke={DATA_COLORS.vo2_rel}
            strokeWidth={dataMode === 'trend' ? 3.5 : 2.5}
            dot={false}
            connectNulls
          />

          {/* FatMax reference line */}
          <ReferenceLine
            x={markers?.fat_max?.power ?? fatMaxPower}
            yAxisId="left"
            stroke="#DC2626"
            strokeDasharray="5 5"
            strokeWidth={2}
          >
            <Label
              value={`FatMax ${markers?.fat_max?.power ?? fatMaxPower}W`}
              position="top"
              dy={-5}
              fill="#DC2626"
              fontSize={11}
              fontWeight={600}
            />
          </ReferenceLine>

          {/* Crossover Point reference line */}
          {crossoverPower && (
            <ReferenceLine
              x={crossoverPower}
              yAxisId="left"
              stroke="#8B5CF6"
              strokeDasharray="3 3"
              strokeWidth={2}
            >
              <Label
                value={`Crossover ${crossoverPower}W`}
                position="insideTop"
                dy={15}
                fill="#8B5CF6"
                fontSize={10}
              />
            </ReferenceLine>
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="mt-2 text-xs text-gray-500">
        Y-left: Fat, CHO · Y-right: VO2/kg
      </div>

      {/* Bottom metrics */}
      <div className="mt-4 pt-4 border-t">
        <div className="flex justify-center items-center gap-8 flex-wrap">
          <div className="text-center">
            <p className="text-xl font-bold text-red-600">
              FatMax: {markers?.fat_max?.power ?? fatMaxPower} W
            </p>
            {mfo && (
              <p className="text-sm text-gray-600">
                MFO: {mfo.toFixed(2)} g/min
              </p>
            )}
            {markers && (
              <p className="text-xs text-gray-500">
                Zone: {fatMaxZoneMin}-{fatMaxZoneMax} W
              </p>
            )}
          </div>

          {crossoverPower && (
            <div className="text-center border-l pl-8">
              <p className="text-xl font-bold text-purple-600">
                Crossover: {crossoverPower} W
              </p>
              {markers?.crossover?.fat_value && (
                <p className="text-sm text-gray-600">
                  Fat = CHO = {markers.crossover.fat_value.toFixed(2)} g/min
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Color Legend */}
      <div className="mt-4 flex justify-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-6 h-1 rounded" style={{ backgroundColor: DATA_COLORS.fat }}></div>
          <span className="text-gray-600">Fat (g/min)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-1 rounded" style={{ backgroundColor: DATA_COLORS.cho }}></div>
          <span className="text-gray-600">CHO (g/min)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-1 rounded" style={{ backgroundColor: DATA_COLORS.vo2_rel }}></div>
          <span className="text-gray-600">VO2/kg (ml/min/kg)</span>
        </div>
      </div>
    </div>
  );
}
