// Sample CPET test data for demonstration
export const sampleTestData = {
  id: "550e8400-e29b-41d4-a716-446655440000",
  test_id: "550e8400-e29b-41d4-a716-446655440000",
  subject_id: "660e8400-e29b-41d4-a716-446655440001",
  test_date: "2024-12-17T11:09:24+09:00",
  protocol_type: "BxB",
  protocol_name: "Ramp Protocol",
  
  metadata: {
    subject_name: "박용두",
    research_id: "SUB-2024-057",
    age: 57,
    gender: "M",
    height_cm: 176,
    weight_kg: 70,
    test_type: "Maximal",
    maximal_effort: "Unconfirmed",
    test_duration: "00:23:59",
    barometric_pressure: 764,
    ambient_temp: 22.5,
    ambient_humidity: 45
  },
  
  phases: {
    rest_end_sec: 180,
    warmup_end_sec: 420,
    exercise_end_sec: 1320,
    peak_sec: 1320,
    recovery_start_sec: 1320,
    total_duration_sec: 1439
  },
  
  summary: {
    vo2_max: 3.45,
    vo2_max_rel: 49.3,
    vo2_max_pred: 3.2,
    vo2_max_percent_pred: 107.8,
    vco2_max: 4.12,
    hr_max: 185,
    hr_max_pred: 163,
    hr_max_percent_pred: 113.5,
    fat_max_hr: 145,
    fat_max_watt: 180,
    fat_max_g_min: 0.68,
    mfo: 0.68,
    fat_max_time_sec: 720,
    rer_max: 1.19,
    vt1_hr: 132,
    vt1_vo2: 2.1,
    vt1_watt: 140,
    vt1_time_sec: 540,
    vt2_hr: 165,
    vt2_vo2: 2.95,
    vt2_watt: 240,
    vt2_time_sec: 960,
    data_quality_score: 92.5
  },
  
  // Abbreviated timeseries for performance (key points only)
  timeseries: [
    { time_sec: 0, phase: "Rest", hr: 111, vo2: 805.4, vco2: 622.3, rer: 0.77, bike_power: 0, fat_oxidation: 0.35, cho_oxidation: 0.12, vo2_rel: 11.5 },
    { time_sec: 60, phase: "Rest", hr: 108, vo2: 850.2, vco2: 680.5, rer: 0.80, bike_power: 0, fat_oxidation: 0.32, cho_oxidation: 0.15, vo2_rel: 12.1 },
    { time_sec: 120, phase: "Rest", hr: 102, vo2: 920.0, vco2: 755.0, rer: 0.82, bike_power: 0, fat_oxidation: 0.28, cho_oxidation: 0.18, vo2_rel: 13.1 },
    { time_sec: 180, phase: "Rest", hr: 95, vo2: 920.5, vco2: 750.2, rer: 0.82, bike_power: 0, fat_oxidation: 0.28, cho_oxidation: 0.15, vo2_rel: 13.1 },
    { time_sec: 240, phase: "Warmup", hr: 100, vo2: 1250.0, vco2: 1000.0, rer: 0.80, bike_power: 40, fat_oxidation: 0.42, cho_oxidation: 0.22, vo2_rel: 17.9 },
    { time_sec: 300, phase: "Warmup", hr: 105, vo2: 1450.3, vco2: 1160.8, rer: 0.80, bike_power: 50, fat_oxidation: 0.48, cho_oxidation: 0.28, vo2_rel: 20.7 },
    { time_sec: 360, phase: "Warmup", hr: 110, vo2: 1680.0, vco2: 1350.0, rer: 0.80, bike_power: 60, fat_oxidation: 0.55, cho_oxidation: 0.32, vo2_rel: 24.0 },
    { time_sec: 420, phase: "Warmup", hr: 115, vo2: 1850.0, vco2: 1480.0, rer: 0.80, bike_power: 75, fat_oxidation: 0.60, cho_oxidation: 0.35, vo2_rel: 26.4 },
    { time_sec: 480, phase: "Exercise", hr: 122, vo2: 1950.0, vco2: 1560.0, rer: 0.80, bike_power: 100, fat_oxidation: 0.64, cho_oxidation: 0.38, vo2_rel: 27.9 },
    { time_sec: 540, phase: "Exercise", hr: 132, vo2: 2100.5, vco2: 1638.0, rer: 0.78, bike_power: 140, fat_oxidation: 0.76, cho_oxidation: 0.45, vo2_rel: 30.0, markers: ["VT1"] },
    { time_sec: 600, phase: "Exercise", hr: 138, vo2: 2350.0, vco2: 1880.0, rer: 0.80, bike_power: 160, fat_oxidation: 0.72, cho_oxidation: 0.52, vo2_rel: 33.6 },
    { time_sec: 660, phase: "Exercise", hr: 142, vo2: 2480.0, vco2: 1984.0, rer: 0.80, bike_power: 170, fat_oxidation: 0.70, cho_oxidation: 0.58, vo2_rel: 35.4 },
    { time_sec: 720, phase: "Exercise", hr: 145, vo2: 2580.0, vco2: 2064.0, rer: 0.80, bike_power: 180, fat_oxidation: 0.68, cho_oxidation: 0.62, vo2_rel: 36.9, markers: ["FATMAX"] },
    { time_sec: 780, phase: "Exercise", hr: 150, vo2: 2680.0, vco2: 2206.0, rer: 0.82, bike_power: 200, fat_oxidation: 0.64, cho_oxidation: 0.72, vo2_rel: 38.3 },
    { time_sec: 840, phase: "Exercise", hr: 155, vo2: 2780.0, vco2: 2392.0, rer: 0.86, bike_power: 210, fat_oxidation: 0.56, cho_oxidation: 0.88, vo2_rel: 39.7 },
    { time_sec: 900, phase: "Exercise", hr: 160, vo2: 2850.0, vco2: 2565.0, rer: 0.90, bike_power: 230, fat_oxidation: 0.45, cho_oxidation: 1.05, vo2_rel: 40.7 },
    { time_sec: 960, phase: "Exercise", hr: 165, vo2: 2950.0, vco2: 2714.0, rer: 0.92, bike_power: 240, fat_oxidation: 0.38, cho_oxidation: 1.15, vo2_rel: 42.1, markers: ["VT2"] },
    { time_sec: 1020, phase: "Exercise", hr: 170, vo2: 3100.0, vco2: 2945.0, rer: 0.95, bike_power: 260, fat_oxidation: 0.28, cho_oxidation: 1.42, vo2_rel: 44.3 },
    { time_sec: 1080, phase: "Exercise", hr: 174, vo2: 3200.0, vco2: 3200.0, rer: 1.00, bike_power: 270, fat_oxidation: 0.20, cho_oxidation: 1.65, vo2_rel: 45.7 },
    { time_sec: 1140, phase: "Exercise", hr: 177, vo2: 3300.0, vco2: 3465.0, rer: 1.05, bike_power: 285, fat_oxidation: 0.18, cho_oxidation: 1.75, vo2_rel: 47.1 },
    { time_sec: 1200, phase: "Exercise", hr: 178, vo2: 3350.0, vco2: 3685.0, rer: 1.10, bike_power: 290, fat_oxidation: 0.15, cho_oxidation: 1.85, vo2_rel: 47.9 },
    { time_sec: 1260, phase: "Exercise", hr: 182, vo2: 3420.0, vco2: 3933.0, rer: 1.15, bike_power: 305, fat_oxidation: 0.08, cho_oxidation: 2.05, vo2_rel: 48.9 },
    { time_sec: 1320, phase: "Peak", hr: 185, vo2: 3450.0, vco2: 4108.0, rer: 1.19, bike_power: 320, fat_oxidation: 0.05, cho_oxidation: 2.15, vo2_rel: 49.3, markers: ["VO2MAX"] },
    { time_sec: 1350, phase: "Recovery", hr: 180, vo2: 2800.0, vco2: 3080.0, rer: 1.10, bike_power: 100, fat_oxidation: 0.10, cho_oxidation: 1.65, vo2_rel: 40.0 },
    { time_sec: 1380, phase: "Recovery", hr: 172, vo2: 2250.0, vco2: 2475.0, rer: 1.10, bike_power: 50, fat_oxidation: 0.08, cho_oxidation: 1.45, vo2_rel: 32.1 },
    { time_sec: 1410, phase: "Recovery", hr: 162, vo2: 1850.0, vco2: 1850.0, rer: 1.00, bike_power: 20, fat_oxidation: 0.20, cho_oxidation: 0.95, vo2_rel: 26.4 },
    { time_sec: 1439, phase: "Recovery", hr: 155, vo2: 1580.0, vco2: 1422.0, rer: 0.90, bike_power: 0, fat_oxidation: 0.25, cho_oxidation: 0.65, vo2_rel: 22.6 }
  ],
  
  markers: {
    fatmax: {
      time_sec: 720,
      hr: 145,
      vo2: 2580.0,
      vo2_rel: 36.9,
      watt: 180,
      rer: 0.80,
      fat_oxidation: 0.68,
      description: "Maximal Fat Oxidation point"
    },
    vo2max: {
      time_sec: 1320,
      hr: 185,
      vo2: 3450.0,
      vo2_rel: 49.3,
      watt: 320,
      rer: 1.19,
      description: "VO2 Peak achieved"
    },
    vt1: {
      time_sec: 540,
      hr: 132,
      vo2: 2100.5,
      vo2_rel: 30.0,
      watt: 140,
      rer: 0.78,
      description: "First Ventilatory Threshold (Aerobic Threshold)"
    },
    vt2: {
      time_sec: 960,
      hr: 165,
      vo2: 2950.0,
      vo2_rel: 42.1,
      watt: 240,
      rer: 0.92,
      description: "Second Ventilatory Threshold (Anaerobic Threshold)"
    }
  }
};

// Sample subjects
export const sampleSubjects = [
  {
    id: "660e8400-e29b-41d4-a716-446655440001",
    research_id: "SUB-2024-057",
    name: "박용두",
    birth_year: 1967,
    gender: "M",
    height_cm: 176,
    weight_kg: 70,
    training_level: "Intermediate",
    metabolic_pattern: "Crossfit", // Fat oxidation peaks early, then declines
    created_at: "2024-01-15T00:00:00Z"
  },
  {
    id: "660e8400-e29b-41d4-a716-446655440002",
    research_id: "SUB-2024-032",
    name: "홍창선",
    birth_year: 1985,
    gender: "M",
    height_cm: 172,
    weight_kg: 68,
    training_level: "Advanced",
    metabolic_pattern: "Hyrox", // Fat oxidation sustained longer
    created_at: "2024-02-20T00:00:00Z"
  },
  {
    id: "660e8400-e29b-41d4-a716-446655440003",
    research_id: "SUB-2024-018",
    name: "김동욱",
    birth_year: 1992,
    gender: "M",
    height_cm: 178,
    weight_kg: 75,
    training_level: "Elite",
    metabolic_pattern: "Hyrox",
    created_at: "2024-03-10T00:00:00Z"
  }
];

// Generate metabolism data for power-based chart
export function generateMetabolismData(subject: typeof sampleSubjects[0]) {
  const data = [];
  const isCrossfit = subject.metabolic_pattern === "Crossfit";
  
  // Generate data from 80W to 260W
  for (let power = 80; power <= 260; power += 10) {
    const normalizedPower = (power - 80) / 180; // 0 to 1
    
    // Fat oxidation curve (peaks earlier for Crossfit, later for Hyrox)
    let fatOxidation;
    if (isCrossfit) {
      // Peaks around 140W, drops faster
      fatOxidation = 400 * Math.exp(-Math.pow((normalizedPower - 0.3) / 0.3, 2));
    } else {
      // Peaks around 180W, sustained longer
      fatOxidation = 380 * Math.exp(-Math.pow((normalizedPower - 0.5) / 0.35, 2));
    }
    
    // CHO oxidation increases with intensity
    const choOxidation = 150 + normalizedPower * 600;
    
    // Total calories
    const totalCalories = fatOxidation + choOxidation;
    
    data.push({
      power,
      fatOxidation: Math.round(fatOxidation),
      choOxidation: Math.round(choOxidation),
      totalCalories: Math.round(totalCalories),
    });
  }
  
  return data;
}

// Get FatMax point for a subject
export function getFatMaxPoint(subject: typeof sampleSubjects[0]) {
  const data = generateMetabolismData(subject);
  let maxFatOxidation = 0;
  let fatMaxPoint = data[0];
  
  data.forEach(point => {
    if (point.fatOxidation > maxFatOxidation) {
      maxFatOxidation = point.fatOxidation;
      fatMaxPoint = point;
    }
  });
  
  const isCrossfit = subject.metabolic_pattern === "Crossfit";
  const duration = isCrossfit ? "2:06" : "2:35";
  const tss = isCrossfit ? 89 : 102;
  
  return {
    ...fatMaxPoint,
    duration,
    tss,
    pattern: subject.metabolic_pattern
  };
}
