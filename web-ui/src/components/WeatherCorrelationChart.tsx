import { useMemo } from 'react';
import { Paper, Text, Group, Stack, ThemeIcon, Badge, Box } from '@mantine/core';
import { TrendingUp, TrendingDown, Minus, Thermometer, Droplet, Wind } from 'lucide-react';

interface DeviceReadings {
  temperature_f?: number;
  humidity?: number;
  [key: string]: number | boolean | undefined;
}

interface Device {
  id: string;
  name: string;
  alias?: string;
  type: string;
  value: number | boolean | null;
  state: 'normal' | 'warning' | 'critical' | 'unknown';
  location?: string;
  zone_id?: string;
  unit?: string;
  trend?: 'up' | 'down' | 'stable';
  readings?: DeviceReadings;
  metadata?: Record<string, string | number>;
}

interface Room {
  id: string;
  name: string;
  type?: string;
  devices: Device[];
}

interface WeatherData {
  weather?: {
    temperature: number;
    humidity: number;
    wind_speed: number;
    description: string;
  };
}

interface WeatherCorrelationChartProps {
  rooms: Room[];
  weather: WeatherData | null;
}

interface CorrelationInsight {
  room: string;
  metric: string;
  deviceName: string;
  indoorValue: number;
  outdoorValue: number;
  delta: number;
  correlation: 'strong' | 'moderate' | 'weak';
  direction: 'up' | 'down' | 'stable';
  unit: string;
}

export default function WeatherCorrelationChart({ rooms, weather }: WeatherCorrelationChartProps) {
  const correlations = useMemo(() => {
    if (!weather?.weather) return [];

    const insights: CorrelationInsight[] = [];

    rooms.forEach((room) => {
      room.devices.forEach((device) => {
        // Use standardized temperature_f from unified contract
        let indoorTemp: number | null = null;

        // Check unified readings object for temperature_f
        if (device.readings?.temperature_f !== undefined) {
          indoorTemp = device.readings.temperature_f;
        }
        // Fallback: Direct value (if device type is temperature)
        else if ((device.type === 'temperature' || device.type === 'temp') && typeof device.value === 'number') {
          indoorTemp = device.value;
        }
        // Backward compatibility: Check metadata for temperature_f
        else if (device.metadata) {
          const tempF = device.metadata['value_temperature_f'];
          if (tempF !== undefined) {
            const parsed = typeof tempF === 'number' ? tempF : parseFloat(String(tempF));
            if (!isNaN(parsed)) {
              indoorTemp = parsed;
            }
          }
        }

        if (indoorTemp !== null && weather.weather) {
          const delta = indoorTemp - weather.weather.temperature;
          const absDelta = Math.abs(delta);

          let correlation: 'strong' | 'moderate' | 'weak' = 'weak';
          if (absDelta < 10) correlation = 'strong';
          else if (absDelta < 20) correlation = 'moderate';

          insights.push({
            room: room.name,
            metric: 'Temperature',
            deviceName: device.alias || device.name,
            indoorValue: indoorTemp,
            outdoorValue: weather.weather.temperature,
            delta,
            correlation,
            direction: delta > 0 ? 'up' : delta < 0 ? 'down' : 'stable',
            unit: '°F',
          });
        }

        // Check for humidity from unified contract
        let indoorHumidity: number | null = null;

        // Check unified readings object for humidity
        if (device.readings?.humidity !== undefined) {
          indoorHumidity = device.readings.humidity;
        }
        // Fallback: Direct value
        else if (device.type === 'humidity' && typeof device.value === 'number') {
          indoorHumidity = device.value;
        }
        // Backward compatibility: Check metadata for humidity
        else if (device.metadata) {
          const humVal = device.metadata['value_Humidity'] || device.metadata['value_humidity'];
          if (humVal !== undefined) {
            const parsed = typeof humVal === 'number' ? humVal : parseFloat(String(humVal));
            if (!isNaN(parsed)) {
              indoorHumidity = parsed;
            }
          }
        }

        if (indoorHumidity !== null && weather.weather) {
          const delta = indoorHumidity - weather.weather.humidity;
          const absDelta = Math.abs(delta);

          let correlation: 'strong' | 'moderate' | 'weak' = 'weak';
          if (absDelta < 10) correlation = 'strong';
          else if (absDelta < 20) correlation = 'moderate';

          insights.push({
            room: room.name,
            metric: 'Humidity',
            deviceName: device.alias || device.name,
            indoorValue: indoorHumidity,
            outdoorValue: weather.weather.humidity,
            delta,
            correlation,
            direction: delta > 0 ? 'up' : delta < 0 ? 'down' : 'stable',
            unit: '%',
          });
        }
      });
    });

    return insights;
  }, [rooms, weather]);

  const getCorrelationColor = (correlation: string) => {
    switch (correlation) {
      case 'strong':
        return 'green';
      case 'moderate':
        return 'yellow';
      case 'weak':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case 'up':
        return <TrendingUp size={16} />;
      case 'down':
        return <TrendingDown size={16} />;
      default:
        return <Minus size={16} />;
    }
  };

  const getMetricIcon = (metric: string) => {
    switch (metric) {
      case 'Temperature':
        return <Thermometer size={18} />;
      case 'Humidity':
        return <Droplet size={18} />;
      default:
        return <Wind size={18} />;
    }
  };

  if (correlations.length === 0) {
    return (
      <Paper p="xl" withBorder>
        <Stack gap="md" align="center">
          <ThemeIcon size="xl" variant="light" color="gray" radius="xl">
            <Thermometer size={32} />
          </ThemeIcon>
          <Stack gap="xs" align="center">
            <Text size="lg" fw={600} ta="center">
              No Temperature/Humidity Sensors Found
            </Text>
            <Text size="sm" c="dimmed" ta="center" maw={500}>
              Weather correlation analysis requires temperature or humidity sensors to compare indoor
              conditions with outdoor weather. Add compatible sensors to your zones to see correlations.
            </Text>
            {weather?.weather && (
              <Box mt="md">
                <Text size="xs" c="dimmed" ta="center">
                  Current outdoor conditions:
                </Text>
                <Group gap="md" justify="center" mt="xs">
                  <Badge size="lg" variant="light" color="blue">
                    {Math.round(weather.weather.temperature)}°F
                  </Badge>
                  <Badge size="lg" variant="light" color="cyan">
                    {weather.weather.humidity}% Humidity
                  </Badge>
                </Group>
              </Box>
            )}
          </Stack>
        </Stack>
      </Paper>
    );
  }

  return (
    <Stack gap="md">
      {correlations.map((insight, idx) => (
        <Paper
          key={idx}
          p="md"
          withBorder
          style={{
            borderLeft: `4px solid var(--mantine-color-${getCorrelationColor(insight.correlation)}-6)`,
          }}
        >
          <Group justify="space-between" wrap="nowrap">
            <Group gap="sm">
              <ThemeIcon
                size="lg"
                variant="light"
                color={getCorrelationColor(insight.correlation)}
              >
                {getMetricIcon(insight.metric)}
              </ThemeIcon>

              <div>
                <Group gap="xs">
                  <Text size="sm" fw={600}>
                    {insight.room}
                  </Text>
                  <Text size="xs" c="dimmed">
                    ({insight.deviceName})
                  </Text>
                </Group>
                <Text size="xs" c="dimmed">
                  {insight.metric}
                </Text>
              </div>
            </Group>

            <Group gap="lg" wrap="nowrap">
              {/* Indoor Value */}
              <Box style={{ textAlign: 'center' }}>
                <Text size="xs" c="dimmed" mb={4}>
                  Indoor
                </Text>
                <Text size="lg" fw={700}>
                  {insight.indoorValue.toFixed(1)}
                  {insight.unit}
                </Text>
              </Box>

              {/* Delta */}
              <Box style={{ textAlign: 'center' }}>
                <Group gap={4} justify="center">
                  {getTrendIcon(insight.direction)}
                  <Text
                    size="md"
                    fw={600}
                    c={
                      insight.direction === 'up'
                        ? 'red'
                        : insight.direction === 'down'
                          ? 'blue'
                          : 'gray'
                    }
                  >
                    {insight.delta > 0 ? '+' : ''}
                    {insight.delta.toFixed(1)}
                    {insight.unit}
                  </Text>
                </Group>
              </Box>

              {/* Outdoor Value */}
              <Box style={{ textAlign: 'center' }}>
                <Text size="xs" c="dimmed" mb={4}>
                  Outdoor
                </Text>
                <Text size="lg" fw={700}>
                  {insight.outdoorValue.toFixed(1)}
                  {insight.unit}
                </Text>
              </Box>

              {/* Correlation Badge */}
              <Badge
                size="lg"
                color={getCorrelationColor(insight.correlation)}
                variant="light"
              >
                {insight.correlation}
              </Badge>
            </Group>
          </Group>
        </Paper>
      ))}
    </Stack>
  );
}
