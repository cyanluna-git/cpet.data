import {
  Area,
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
  Scatter
} from 'recharts';
import type { ProcessedSeries, MetabolicMarkers } from '@/lib/api';

export type DataMode = 'smoothed' | 'binned' | 'raw';

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
  title = "METABOLISM",
  subjectName,
  processedSeries,
  markers,
  dataMode = 'smoothed',
  showRawOverlay = false
}: MetabolismChartProps) {

  // Find the hour marker (around 239W for "1 hour")
  const hourMarkerPower = 239;

  // Get FatMax zone from markers or use default
  const fatMaxZoneMin = markers?.fat_max?.zone_min ?? fatMaxPower - 20;
  const fatMaxZoneMax = markers?.fat_max?.zone_max ?? fatMaxPower + 20;
  const mfo = markers?.fat_max?.mfo;

  // Get Crossover point from markers
  const crossoverPower = markers?.crossover?.power;

  // Transform processed series data based on dataMode
  const getChartData = () => {
    if (!processedSeries) {
      return data;
    }

    let sourceData: Array<{ power: number; fat_oxidation: number | null; cho_oxidation: number | null }>;

    switch (dataMode) {
      case 'raw':
        sourceData = processedSeries.raw;
        break;
      case 'binned':
        sourceData = processedSeries.binned;
        break;
      case 'smoothed':
      default:
        sourceData = processedSeries.smoothed;
        break;
    }

    // Convert g/min to kcal/day for display (matching existing format)
    return sourceData.map(point => ({
      power: point.power,
      fatOxidation: point.fat_oxidation !== null ? Math.round(point.fat_oxidation * 9.75 * 60 * 24) : 0,
      choOxidation: point.cho_oxidation !== null ? Math.round(point.cho_oxidation * 4.07 * 60 * 24) : 0,
      totalCalories: point.fat_oxidation !== null && point.cho_oxidation !== null
        ? Math.round((point.fat_oxidation * 9.75 + point.cho_oxidation * 4.07) * 60 * 24)
        : 0,
    })).filter(d => d.power >= 50 && d.power <= 300).sort((a, b) => a.power - b.power);
  };

  // Get raw/binned scatter data for overlay
  const getOverlayData = () => {
    if (!processedSeries || !showRawOverlay) return null;

    // Show binned data as scatter when in smoothed mode
    const overlaySource = dataMode === 'smoothed' ? processedSeries.binned : processedSeries.raw;

    return overlaySource.map(point => ({
      power: point.power,
      fatOxidation: point.fat_oxidation !== null ? Math.round(point.fat_oxidation * 9.75 * 60 * 24) : 0,
      choOxidation: point.cho_oxidation !== null ? Math.round(point.cho_oxidation * 4.07 * 60 * 24) : 0,
    })).filter(d => d.power >= 50 && d.power <= 300);
  };

  const chartData = processedSeries ? getChartData() : data;
  const overlayData = getOverlayData();

  // Calculate domain
  const maxY = Math.max(...chartData.map(d => d.totalCalories || d.fatOxidation + d.choOxidation), 1000);
  const yDomain = [0, Math.ceil(maxY / 200) * 200];

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-teal-600 mb-1">{title}</h2>
        {subjectName && (
          <p className="text-sm text-gray-600">{subjectName}</p>
        )}
        {processedSeries && (
          <p className="text-xs text-gray-500 mt-1">
            Data: {dataMode === 'smoothed' ? 'LOESS Smoothed' : dataMode === 'binned' ? '10W Binned' : 'Raw'}
            {showRawOverlay && dataMode === 'smoothed' && ' + Binned overlay'}
          </p>
        )}
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
          syncId="metabolicProfile"
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="power"
            type="number"
            domain={[80, 260]}
            ticks={[80, 100, 120, 140, 160, 180, 200, 220, 240, 260]}
            label={{ value: 'Power (W)', position: 'insideBottom', offset: -10, style: { fill: '#6b7280' } }}
            tick={{ fill: '#6b7280', fontSize: 12 }}
          />
          <YAxis
            label={{ value: 'Calories', angle: -90, position: 'insideLeft', style: { fill: '#6b7280' } }}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            domain={yDomain}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const dataPoint = payload[0].payload;
                return (
                  <div className="bg-white p-3 border border-gray-300 rounded shadow-lg">
                    <p className="font-semibold text-sm mb-1">{`${dataPoint.power} W`}</p>
                    <p className="text-xs text-gray-600">{`지방 연소: ${dataPoint.fatOxidation} Cal`}</p>
                    <p className="text-xs text-gray-600">{`탄수화물: ${dataPoint.choOxidation} Cal`}</p>
                    <p className="text-xs text-gray-800 font-semibold">{`총 칼로리: ${dataPoint.totalCalories} Cal`}</p>
                  </div>
                );
              }
              return null;
            }}
          />

          {/* FatMax Zone (Background highlight) */}
          {markers && (
            <ReferenceArea
              x1={fatMaxZoneMin}
              x2={fatMaxZoneMax}
              fill="#fef3c7"
              fillOpacity={0.4}
              strokeOpacity={0}
            />
          )}

          {/* Total calories line */}
          <Line
            type="monotone"
            dataKey="totalCalories"
            stroke="#9ca3af"
            strokeWidth={2}
            dot={false}
            name="총 칼로리"
          />

          {/* Fat oxidation area */}
          <Area
            type="monotone"
            dataKey="fatOxidation"
            stackId="1"
            stroke="#fbbf24"
            fill="#fef3c7"
            name="지방 연소"
          />

          {/* CHO oxidation area */}
          <Area
            type="monotone"
            dataKey="choOxidation"
            stackId="1"
            stroke="#14b8a6"
            fill="#99f6e4"
            name="탄수화물 연소"
          />

          {/* Overlay scatter for raw/binned data */}
          {overlayData && (
            <>
              <Scatter
                data={overlayData}
                dataKey="fatOxidation"
                fill="#f59e0b"
                opacity={0.4}
                name="Binned Fat"
              />
              <Scatter
                data={overlayData}
                dataKey="choOxidation"
                fill="#0d9488"
                opacity={0.4}
                name="Binned CHO"
              />
            </>
          )}

          {/* FatMax reference line */}
          <ReferenceLine
            x={markers?.fat_max?.power ?? fatMaxPower}
            stroke="#dc2626"
            strokeDasharray="5 5"
            strokeWidth={2}
          >
            <Label
              value={`FatMax ${markers?.fat_max?.power ?? fatMaxPower}W`}
              position="top"
              style={{
                fill: '#1f2937',
                fontWeight: 'bold',
                fontSize: 12,
              }}
              angle={-90}
              offset={15}
            />
          </ReferenceLine>

          {/* Crossover Point reference line */}
          {crossoverPower && (
            <ReferenceLine
              x={crossoverPower}
              stroke="#8b5cf6"
              strokeDasharray="3 3"
              strokeWidth={2}
            >
              <Label
                value={`Crossover ${crossoverPower}W`}
                position="top"
                style={{
                  fill: '#7c3aed',
                  fontWeight: '600',
                  fontSize: 11,
                }}
                angle={-90}
                offset={10}
              />
            </ReferenceLine>
          )}

          {/* Hour marker reference line */}
          <ReferenceLine
            x={hourMarkerPower}
            stroke="#6b7280"
            strokeDasharray="3 3"
            strokeWidth={1}
          >
            <Label
              value={`1 hour: ${hourMarkerPower}W`}
              position="top"
              style={{
                fill: '#ec4899',
                fontWeight: '600',
                fontSize: 11,
              }}
              angle={-90}
              offset={10}
            />
          </ReferenceLine>
        </ComposedChart>
      </ResponsiveContainer>

      {/* Bottom metrics */}
      <div className="mt-6 text-center border-t pt-4">
        <div className="flex justify-center items-center gap-8 flex-wrap">
          <div>
            <p className="text-2xl font-bold text-gray-800">
              FatMax : {markers?.fat_max?.power ?? fatMaxPower} W
            </p>
            {mfo && (
              <p className="text-sm text-orange-600">
                MFO: {mfo.toFixed(2)} g/min
              </p>
            )}
            {markers && (
              <p className="text-sm text-amber-600">
                Zone: {fatMaxZoneMin}-{fatMaxZoneMax} W
              </p>
            )}
          </div>

          {crossoverPower && (
            <div className="border-l pl-8">
              <p className="text-xl font-bold text-purple-700">
                Crossover : {crossoverPower} W
              </p>
              {markers?.crossover?.fat_value && (
                <p className="text-sm text-gray-600">
                  Fat = CHO = {markers.crossover.fat_value.toFixed(2)} g/min
                </p>
              )}
            </div>
          )}
        </div>

        <p className="text-lg text-gray-600 mt-3">
          Duration : {duration}, TSS : {tss}
        </p>
      </div>

      {/* Legend */}
      <div className="mt-4 flex justify-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-yellow-200 border border-yellow-500 rounded"></div>
          <span className="text-gray-600">지방 연소</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-teal-200 border border-teal-500 rounded"></div>
          <span className="text-gray-600">탄수화물 연소</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-1 bg-red-500"></div>
          <span className="text-gray-600">FatMax</span>
        </div>
        {crossoverPower && (
          <div className="flex items-center gap-2">
            <div className="w-4 h-1 bg-purple-500"></div>
            <span className="text-gray-600">Crossover</span>
          </div>
        )}
        {markers && (
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-amber-100 border border-amber-300 rounded"></div>
            <span className="text-gray-600">FatMax Zone (90%)</span>
          </div>
        )}
      </div>
    </div>
  );
}
