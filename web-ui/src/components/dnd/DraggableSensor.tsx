import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { Paper, Group, Text, ThemeIcon, Badge, Stack } from '@mantine/core';
import {
  Thermometer,
  Droplet,
  Zap,
  Battery,
  BatteryLow,
  AlertTriangle,
  GripVertical,
  Activity,
  Radio,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { TimeAgo, Sparkline } from '../shared';
import { API_BASE_WITH_PATHS as API_BASE } from '../../apiConfig';
import type { Device, DeviceReadings } from './types';

interface DraggableSensorProps {
  device: Device;
  editMode: boolean;
  onClick?: () => void;
  isRecentlyUpdated?: boolean;
}

// Determine device icon based on readings/metadata/type
function getDeviceIcon(device: Device) {
  const readings = device.readings || {};
  const metadata = device.metadata || {};
  const model = (metadata.model || '').toLowerCase();
  const name = (device.name || '').toLowerCase();
  const displayName = (device.display_name || '').toLowerCase();

  // Check for water/leak sensors
  if (
    'Water Alarm' in readings ||
    'water' in readings ||
    model.includes('water') ||
    model.includes('leak') ||
    name.includes('leak') ||
    displayName.includes('leak') ||
    displayName.includes('water')
  ) {
    return { icon: Droplet, color: 'blue' };
  }

  // Check for temperature sensors
  if (
    'temperature_f' in readings ||
    model.includes('temp') ||
    model.includes('zse44') ||
    name.includes('temp')
  ) {
    return { icon: Thermometer, color: 'orange' };
  }

  // Check for humidity sensors
  if ('Humidity' in readings || 'humidity' in readings) {
    return { icon: Droplet, color: 'cyan' };
  }

  // Check for motion sensors
  if (model.includes('motion') || name.includes('motion')) {
    return { icon: Activity, color: 'violet' };
  }

  // Default based on device type
  if (device.type === 'sensor') {
    return { icon: Radio, color: 'gray' };
  }

  return { icon: Zap, color: 'gray' };
}

// Extract meaningful readings to display
function getDisplayReadings(readings: DeviceReadings | undefined): Array<{ label: string; value: string; icon: any }> {
  if (!readings) return [];

  const display: Array<{ label: string; value: string; icon: any }> = [];

  // Temperature - use standardized temperature_f property (backend converts all temps to Fahrenheit)
  const temp = readings['temperature_f'];
  if (temp !== undefined && temp !== 0 && typeof temp === 'number') {
    display.push({
      label: 'Temp',
      value: `${temp.toFixed(1)}°F`,
      icon: Thermometer,
    });
  }

  // Humidity - prefer "Humidity" over raw "humidity"
  const humidity = readings.humidity
  if (humidity !== undefined && humidity !== 0 && typeof humidity === 'number') {
    display.push({
      label: 'Humidity',
      value: `${humidity}%`,
      icon: Droplet,
    });
  }

  // Water leak status
  const water = readings.water;
  if (water !== undefined) {
    // Handle boolean or number values (objects are ignored)
    const waterValue = typeof water === 'object' ? false : water;
    display.push({
      label: 'Water',
      value: waterValue === 0 || waterValue === false ? 'Dry' : 'LEAK!',
      icon: Droplet,
    });
  }

  return display;
}


interface ReadingTrend {
  current: number;
  previous?: number;
  delta?: number;
  direction?: 'up' | 'down' | 'stable';
}

export function DraggableSensor({
  device,
  editMode,
  onClick,
  isRecentlyUpdated = false,
}: DraggableSensorProps) {
  const [sparklineData, setSparklineData] = useState<number[]>([]);
  const [tempTrend, setTempTrend] = useState<ReadingTrend | null>(null);
  const [humidityTrend, setHumidityTrend] = useState<ReadingTrend | null>(null);

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: device.id,
    data: { device },
    disabled: !editMode,
  });

  // Fetch sparkline data and calculate trends for temperature sensors
  useEffect(() => {
    const temp = device.readings?.temperature_f;
    const humidity = device.readings?.humidity;

    if ((!temp || temp === 0) && (!humidity || humidity === 0)) return;

    const fetchHistory = async () => {
      try {
        // Fetch recent readings for trend calculation (24 hours for sparse sensor data)
        const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

        // Fetch temperature trend
        if (temp && temp > 0) {
          const tempResponse = await fetch(
            `${API_BASE}/sensors/${device.id}/readings?type=temperature&since=${since}&limit=20`
          );
          if (tempResponse.ok) {
            const readings = await tempResponse.json();
            if (Array.isArray(readings) && readings.length > 0) {
              const temps = readings.map((r: { value: number }) => r.value).filter((v: number) => v > 0);
              setSparklineData(temps);

              // Calculate trend from last two readings
              if (temps.length >= 2) {
                const current = temps[temps.length - 1];
                const previous = temps[temps.length - 2];
                const delta = current - previous;
                setTempTrend({
                  current,
                  previous,
                  delta,
                  direction: Math.abs(delta) < 0.1 ? 'stable' : delta > 0 ? 'up' : 'down',
                });
              }
            }
          }
        }

        // Fetch humidity trend
        if (humidity && humidity > 0) {
          const humidityResponse = await fetch(
            `${API_BASE}/sensors/${device.id}/readings?type=humidity&since=${since}&limit=20`
          );
          if (humidityResponse.ok) {
            const readings = await humidityResponse.json();
            if (Array.isArray(readings) && readings.length > 0) {
              const humidities = readings.map((r: { value: number }) => r.value).filter((v: number) => v > 0);

              if (humidities.length >= 2) {
                const current = humidities[humidities.length - 1];
                const previous = humidities[humidities.length - 2];
                const delta = current - previous;
                setHumidityTrend({
                  current,
                  previous,
                  delta,
                  direction: Math.abs(delta) < 1 ? 'stable' : delta > 0 ? 'up' : 'down',
                });
              }
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch trend data:', error);
      }
    };

    fetchHistory();
  }, [device.id, device.readings?.temperature_f, device.readings?.humidity]);

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.5 : 1,
    cursor: editMode ? 'grab' : 'pointer',
    transition: isDragging ? undefined : 'all 0.3s ease-in-out',
    borderWidth: device.active || device.state === 'critical' ? '2px' : '1px',
    borderColor:
      device.active || device.state === 'critical'
        ? 'var(--mantine-color-red-6)'
        : device.state === 'warning'
          ? 'var(--mantine-color-yellow-6)'
          : isRecentlyUpdated
            ? 'var(--mantine-color-blue-5)'
            : undefined,
    backgroundColor:
      device.active || device.state === 'critical'
        ? 'var(--mantine-color-red-0)'
        : device.state === 'warning'
          ? 'var(--mantine-color-yellow-0)'
          : isRecentlyUpdated
            ? 'var(--mantine-color-blue-0)'
            : undefined,
    boxShadow:
      device.active || device.state === 'critical'
        ? '0 0 20px rgba(250, 82, 82, 0.5)'
        : device.state === 'warning'
          ? '0 0 15px rgba(250, 176, 5, 0.3)'
          : undefined,
  };

  const { icon: DeviceIcon, color: iconColor } = getDeviceIcon(device);
  const displayReadings = getDisplayReadings(device.readings);

  return (
    <Paper
      ref={setNodeRef}
      p="sm"
      radius="md"
      withBorder
      style={style}
      onClick={editMode ? undefined : onClick}
      {...(editMode ? { ...listeners, ...attributes } : {})}
    >
      <Stack gap={4}>
        {/* Header row: icon, name, battery, alert */}
        <Group justify="space-between">
          <Group gap="xs">
            {editMode && (
              <GripVertical
                size={14}
                style={{ color: 'var(--mantine-color-dimmed)', cursor: 'grab' }}
              />
            )}
            <ThemeIcon
              size="sm"
              variant="light"
              color={device.state === 'critical' || device.active ? 'red' : iconColor}
            >
              <DeviceIcon size={14} />
            </ThemeIcon>
            <div>
              <Text size="sm" fw={500}>
                {device.display_name || device.name}
              </Text>
              <TimeAgo timestamp={device.last_updated} />
            </div>
          </Group>
          <Group gap="xs">
            {device.battery?.level !== undefined &&
             device.battery?.level > 0 &&
             device.metadata?.is_listening !== 'true' && (
              <Group gap={2}>
                {device.battery?.level < 20 ? (
                  <BatteryLow size={14} color="var(--mantine-color-red-6)" />
                ) : (
                  <Battery
                    size={14}
                    color={
                      device.battery?.level < 40
                        ? 'var(--mantine-color-yellow-6)'
                        : 'var(--mantine-color-green-6)'
                    }
                  />
                )}
                <Text
                  size="xs"
                  c={
                    device.battery?.level < 20
                      ? 'red'
                      : device.battery?.level < 40
                        ? 'yellow'
                        : 'dimmed'
                  }
                >
                  {device.battery?.level}%
                </Text>
              </Group>
            )}
            {device.active && (
              <ThemeIcon size="xs" color="red" variant="filled">
                <AlertTriangle size={10} />
              </ThemeIcon>
            )}
          </Group>
        </Group>

        {/* Readings row with trends and sparkline */}
        {displayReadings.length > 0 && (
          <Group gap="xs" ml={editMode ? 28 : 22} align="center" wrap="nowrap">
            {displayReadings.map((reading) => {
              const ReadingIcon = reading.icon;
              const isAlert = reading.value === 'LEAK!';
              const isTemp = reading.label === 'Temp';
              const isHumidity = reading.label === 'Humidity';

              // Get trend info
              const trend = isTemp ? tempTrend : isHumidity ? humidityTrend : null;
              const showTrend = trend && trend.direction !== 'stable' && trend.delta !== undefined;

              return (
                <Group key={reading.label} gap={4}>
                  <Badge
                    size="sm"
                    variant="light"
                    color={isAlert ? 'red' : 'gray'}
                    leftSection={<ReadingIcon size={10} />}
                  >
                    {reading.value}
                  </Badge>
                  {showTrend && trend.delta !== undefined && (
                    <Group gap={2}>
                      {trend.direction === 'up' ? (
                        <TrendingUp size={10} color="var(--mantine-color-red-6)" />
                      ) : (
                        <TrendingDown size={10} color="var(--mantine-color-blue-6)" />
                      )}
                      <Text size="xs" c={trend.direction === 'up' ? 'red' : 'blue'}>
                        {isTemp
                          ? `${Math.abs(trend.delta).toFixed(1)}°`
                          : `${Math.abs(trend.delta).toFixed(0)}%`
                        }
                      </Text>
                    </Group>
                  )}
                </Group>
              );
            })}
            {sparklineData.length > 2 && (
              <Sparkline data={sparklineData} width={50} height={16} />
            )}
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
