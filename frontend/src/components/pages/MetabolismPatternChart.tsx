import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from 'recharts';

interface MetabolismPatternChartProps {
  pattern: 'Crossfit' | 'Hyrox';
}

export function MetabolismPatternChart({ pattern }: MetabolismPatternChartProps) {
  // Generate pattern data
  const generatePatternData = () => {
    const data = [];
    const steps = 50;
    
    for (let i = 0; i <= steps; i++) {
      const x = i / steps; // 0 to 1
      
      let fatCurve, choCurve;
      
      if (pattern === 'Crossfit') {
        // Fat peaks early, drops off
        fatCurve = 0.3 + 0.7 * Math.exp(-Math.pow((x - 0.25) / 0.25, 2));
        // CHO increases linearly but starts lower
        choCurve = 0.1 + x * 0.85;
      } else {
        // Hyrox: Fat peaks later, sustained longer
        fatCurve = 0.2 + 0.8 * Math.exp(-Math.pow((x - 0.5) / 0.3, 2));
        // CHO increases more steeply
        choCurve = 0.05 + Math.pow(x, 1.2) * 0.95;
      }
      
      data.push({
        x: i,
        fat: fatCurve,
        cho: choCurve,
      });
    }
    
    return data;
  };
  
  const data = generatePatternData();
  
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-xl font-semibold text-gray-800 mb-4 text-center">
        {pattern}
      </h3>
      
      <ResponsiveContainer width="100%" height={250}>
        <LineChart
          data={data}
          margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
        >
          <XAxis dataKey="x" hide />
          <YAxis hide domain={[0, 1]} />
          
          {/* Fat oxidation curve (blue) */}
          <Line
            type="monotone"
            dataKey="fat"
            stroke="#1e40af"
            strokeWidth={3}
            dot={false}
            isAnimationActive={false}
          />
          
          {/* CHO oxidation line (red) */}
          <Line
            type="monotone"
            dataKey="cho"
            stroke="#dc2626"
            strokeWidth={3}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
