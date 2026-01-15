import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Label,
  ComposedChart
} from 'recharts';

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
}

export function MetabolismChart({
  data,
  fatMaxPower,
  duration = "2:06",
  tss = 89,
  title = "METABOLISM",
  subjectName
}: MetabolismChartProps) {
  
  // Find the hour marker (around 239W for "1 hour")
  const hourMarkerPower = 239;
  
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-teal-600 mb-1">{title}</h2>
        {subjectName && (
          <p className="text-sm text-gray-600">{subjectName}</p>
        )}
      </div>
      
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={data}
          margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
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
            domain={[0, 1000]}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                return (
                  <div className="bg-white p-3 border border-gray-300 rounded shadow-lg">
                    <p className="font-semibold text-sm mb-1">{`${payload[0].payload.power} W`}</p>
                    <p className="text-xs text-gray-600">{`지방 연소: ${payload[0].payload.fatOxidation} Cal`}</p>
                    <p className="text-xs text-gray-600">{`탄수화물: ${payload[0].payload.choOxidation} Cal`}</p>
                    <p className="text-xs text-gray-800 font-semibold">{`총 칼로리: ${payload[0].payload.totalCalories} Cal`}</p>
                  </div>
                );
              }
              return null;
            }}
          />
          
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
          
          {/* FatMax reference line */}
          <ReferenceLine
            x={fatMaxPower}
            stroke="#dc2626"
            strokeDasharray="5 5"
            strokeWidth={2}
          >
            <Label
              value={`FatMax ${fatMaxPower}W`}
              position="top"
              style={{
                fill: '#1f2937',
                fontWeight: 'bold',
                fontSize: 12,
                transform: 'rotate(-90deg)',
                transformOrigin: 'center'
              }}
              angle={-90}
              offset={15}
            />
          </ReferenceLine>
          
          {/* Hour marker reference line */}
          <ReferenceLine
            x={hourMarkerPower}
            stroke="#6b7280"
            strokeDasharray="3 3"
            strokeWidth={1}
          >
            <Label
              value={`1 hour: ${hourMarkerPower}W, ${data.find(d => d.power === 240)?.totalCalories || 864} kcal`}
              position="top"
              style={{
                fill: '#ec4899',
                fontWeight: '600',
                fontSize: 11,
                transform: 'rotate(-90deg)',
                transformOrigin: 'center'
              }}
              angle={-90}
              offset={10}
            />
          </ReferenceLine>
          
          {/* FatMax highlighted region */}
          <rect
            x={`${((fatMaxPower - 80) / 180) * 100}%`}
            y="0"
            width="6%"
            height="100%"
            fill="#fef3c7"
            fillOpacity={0.3}
          />
        </ComposedChart>
      </ResponsiveContainer>
      
      {/* Bottom metrics */}
      <div className="mt-6 text-center border-t pt-4">
        <p className="text-2xl font-bold text-gray-800 mb-2">
          FatMax : {fatMaxPower} W
        </p>
        <p className="text-lg text-gray-600">
          Duration : {duration}, TSS : {tss}
        </p>
      </div>
    </div>
  );
}
