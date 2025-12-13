import { useEffect, useState } from 'react';
import { Card, Stack, Text, Loader, Group, Select, Paper, Box } from '@mantine/core';
import { Thermometer, Droplets, TrendingUp, TrendingDown, Activity, Droplet } from 'lucide-react';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;

interface SensorReading {
  id: number;
  device_id: string;
  reading_type: string;
  value: number;
  unit: string;
  outdoor_temp?: number;
  timestamp: string;
}

interface SensorTimeSeriesChartProps {
  deviceId: string;
}

interface ChartData {
  values: number[];
  timestamps: Date[];
  min: number;
  max: number;
  avg: number;
  trend: 'up' | 'down' | 'stable';
}

function processReadings(readings: SensorReading[]): ChartData {
  if (readings.length === 0) {
    return { values: [], timestamps: [], min: 0, max: 0, avg: 0, trend: 'stable' };
  }

  const values = readings.map(r => r.value).reverse();
  const timestamps = readings.map(r => new Date(r.timestamp)).reverse();
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((sum, v) => sum + v, 0) / values.length;

  // Calculate trend: compare first third vs last third
  const thirdSize = Math.floor(values.length / 3);
  const firstThird = values.slice(0, thirdSize).reduce((sum, v) => sum + v, 0) / thirdSize;
  const lastThird = values.slice(-thirdSize).reduce((sum, v) => sum + v, 0) / thirdSize;
  const diff = lastThird - firstThird;
  const trend = Math.abs(diff) < 0.5 ? 'stable' : diff > 0 ? 'up' : 'down';

  return { values, timestamps, min, max, avg, trend };
}

function formatXAxisLabel(date: Date, index: number, totalPoints: number): string {
  // Show fewer labels to avoid crowding
  const showEvery = Math.ceil(totalPoints / 6); // Show ~6 labels max
  if (index % showEvery !== 0 && index !== totalPoints - 1) return '';

  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  if (isToday) {
    // Today: show time only
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  } else {
    // Other days: show date + time
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + '\n' +
           date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  }
}

function MiniLineChart({
  data,
  color,
  width = 600,
  height = 150
}: {
  data: ChartData;
  color: string;
  width?: number;
  height?: number;
}) {
  if (data.values.length < 2) {
    return (
      <Text size="sm" c="dimmed" ta="center">
        Not enough data points
      </Text>
    );
  }

  const { values, timestamps, min, max } = data;
  const range = max - min || 1;
  const paddingLeft = 40;
  const paddingRight = 10;
  const paddingTop = 10;
  const paddingBottom = 40;
  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  // Generate SVG path
  const points = values.map((value, index) => {
    const x = paddingLeft + (index / (values.length - 1)) * chartWidth;
    const y = paddingTop + chartHeight - ((value - min) / range) * chartHeight;
    return `${x},${y}`;
  });

  const pathData = `M ${points.join(' L ')}`;
  const areaPath = `${pathData} L ${width - paddingRight},${height - paddingBottom} L ${paddingLeft},${height - paddingBottom} Z`;

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {/* Horizontal grid lines */}
      <line x1={paddingLeft} y1={paddingTop} x2={width - paddingRight} y2={paddingTop} stroke="#e9ecef" strokeWidth="1" />
      <line x1={paddingLeft} y1={paddingTop + chartHeight / 2} x2={width - paddingRight} y2={paddingTop + chartHeight / 2} stroke="#e9ecef" strokeWidth="1" strokeDasharray="2,2" />
      <line x1={paddingLeft} y1={height - paddingBottom} x2={width - paddingRight} y2={height - paddingBottom} stroke="#e9ecef" strokeWidth="1" />

      {/* Y-axis labels */}
      <text x={paddingLeft - 5} y={paddingTop} textAnchor="end" fontSize="10" fill="#868e96" dominantBaseline="middle">
        {max.toFixed(1)}
      </text>
      <text x={paddingLeft - 5} y={paddingTop + chartHeight / 2} textAnchor="end" fontSize="10" fill="#868e96" dominantBaseline="middle">
        {((max + min) / 2).toFixed(1)}
      </text>
      <text x={paddingLeft - 5} y={height - paddingBottom} textAnchor="end" fontSize="10" fill="#868e96" dominantBaseline="middle">
        {min.toFixed(1)}
      </text>

      {/* X-axis labels */}
      {timestamps.map((timestamp, i) => {
        const label = formatXAxisLabel(timestamp, i, timestamps.length);
        if (!label) return null;

        const x = paddingLeft + (i / (values.length - 1)) * chartWidth;
        const lines = label.split('\n');

        return (
          <g key={i}>
            {lines.map((line, lineIndex) => (
              <text
                key={lineIndex}
                x={x}
                y={height - paddingBottom + 15 + (lineIndex * 12)}
                textAnchor="middle"
                fontSize="9"
                fill="#868e96"
              >
                {line}
              </text>
            ))}
          </g>
        );
      })}

      {/* Area fill */}
      <path d={areaPath} fill={color} fillOpacity="0.1" />

      {/* Line */}
      <path
        d={pathData}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Points */}
      {points.map((point, i) => {
        const [x, y] = point.split(',').map(Number);
        return (
          <circle key={i} cx={x} cy={y} r={2} fill={color} />
        );
      })}
    </svg>
  );
}

export function SensorTimeSeriesChart({ deviceId }: SensorTimeSeriesChartProps) {
  const [sensorData, setSensorData] = useState<Record<string, SensorReading[]>>({});
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('24');

  useEffect(() => {
    async function fetchReadings() {
      setLoading(true);
      try {
        const hoursBack = parseInt(timeRange);
        const since = new Date(Date.now() - hoursBack * 60 * 60 * 1000).toISOString();

        // Fetch all reading types for this device
        const readingTypes = ['temperature', 'humidity', 'water', 'motion', 'contact', 'power', 'energy'];
        const data: Record<string, SensorReading[]> = {};

        await Promise.all(
          readingTypes.map(async (type) => {
            const res = await fetch(
              `${API_BASE}/sensors/${deviceId}/readings?type=${type}&since=${since}&limit=1000`
            );
            if (res.ok) {
              const readings = await res.json();
              if (Array.isArray(readings) && readings.length > 0) {
                data[type] = readings;
              }
            }
          })
        );

        setSensorData(data);
      } catch (error) {
        console.error('Failed to fetch sensor readings:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchReadings();
  }, [deviceId, timeRange]);

  const hasData = Object.keys(sensorData).length > 0;

  if (loading) {
    return (
      <Card withBorder p="lg">
        <Stack align="center" gap="md">
          <Loader size="md" />
          <Text size="sm" c="dimmed">Loading sensor history...</Text>
        </Stack>
      </Card>
    );
  }

  if (!hasData) {
    return (
      <Card withBorder p="lg">
        <Stack align="center" gap="md">
          <Text size="lg" fw={600}>No Time-Series Data</Text>
          <Text size="sm" c="dimmed" ta="center">
            This device hasn't reported any sensor readings yet.
            Data will appear here once the device starts reporting.
          </Text>
        </Stack>
      </Card>
    );
  }

  const getSensorConfig = (type: string) => {
    switch (type) {
      case 'temperature':
        return { icon: Thermometer, color: '#228be6', label: 'Temperature', unit: '°F', bgColor: 'blue.0' };
      case 'humidity':
        return { icon: Droplets, color: '#12b886', label: 'Humidity', unit: '%', bgColor: 'cyan.0' };
      case 'water':
        return { icon: Droplet, color: '#fa5252', label: 'Water/Leak', unit: '', bgColor: 'red.0' };
      case 'motion':
        return { icon: Activity, color: '#fd7e14', label: 'Motion', unit: '', bgColor: 'orange.0' };
      case 'contact':
        return { icon: Activity, color: '#7950f2', label: 'Contact', unit: '', bgColor: 'violet.0' };
      case 'power':
        return { icon: Activity, color: '#fab005', label: 'Power', unit: 'W', bgColor: 'yellow.0' };
      case 'energy':
        return { icon: Activity, color: '#fab005', label: 'Energy', unit: 'kWh', bgColor: 'yellow.0' };
      default:
        return { icon: Activity, color: '#868e96', label: type, unit: '', bgColor: 'gray.0' };
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <Text fw={600} size="lg">Sensor History</Text>
        <Select
          value={timeRange}
          onChange={(value) => setTimeRange(value || '24')}
          data={[
            { value: '1', label: 'Last Hour' },
            { value: '6', label: 'Last 6 Hours' },
            { value: '24', label: 'Last 24 Hours' },
            { value: '48', label: 'Last 48 Hours' },
            { value: '168', label: 'Last Week' },
          ]}
          w={150}
        />
      </Group>

      {Object.entries(sensorData).map(([type, readings]) => {
        const config = getSensorConfig(type);
        const Icon = config.icon;
        const chartData = processReadings(readings);

        return (
          <Card key={type} withBorder p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="flex-start">
                <Group gap="sm">
                  <Icon size={24} color={config.color} />
                  <div>
                    <Text fw={600} size="lg">{config.label}</Text>
                    <Text size="xs" c="dimmed">{readings.length} readings</Text>
                  </div>
                </Group>

                <Paper p="sm" withBorder bg={config.bgColor}>
                  <Group gap="lg">
                    <Box>
                      <Text size="xs" c="dimmed">Min</Text>
                      <Text size="sm" fw={600}>{chartData.min.toFixed(1)}{config.unit}</Text>
                    </Box>
                    <Box>
                      <Text size="xs" c="dimmed">Avg</Text>
                      <Text size="sm" fw={600}>{chartData.avg.toFixed(1)}{config.unit}</Text>
                    </Box>
                    <Box>
                      <Text size="xs" c="dimmed">Max</Text>
                      <Text size="sm" fw={600}>{chartData.max.toFixed(1)}{config.unit}</Text>
                    </Box>
                    <Box>
                      <Text size="xs" c="dimmed">Trend</Text>
                      <Group gap={4}>
                        {chartData.trend === 'up' ? (
                          <TrendingUp size={16} color={type === 'temperature' ? '#fa5252' : '#12b886'} />
                        ) : chartData.trend === 'down' ? (
                          <TrendingDown size={16} color={type === 'temperature' ? '#228be6' : '#fa5252'} />
                        ) : null}
                        <Text
                          size="sm"
                          fw={600}
                          c={chartData.trend === 'up' ? (type === 'temperature' ? 'red' : 'teal') : chartData.trend === 'down' ? (type === 'temperature' ? 'blue' : 'red') : 'gray'}
                        >
                          {chartData.trend}
                        </Text>
                      </Group>
                    </Box>
                  </Group>
                </Paper>
              </Group>

              <MiniLineChart data={chartData} color={config.color} width={600} height={150} />
            </Stack>
          </Card>
        );
      })}
    </Stack>
  );
}
