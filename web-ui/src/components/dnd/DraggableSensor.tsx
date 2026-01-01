import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { Paper, Group, Text, ThemeIcon, Stack } from '@mantine/core';
import { Sparkline } from '@mantine/charts';
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
  Minus,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { TimeAgo } from '../shared';
import { API_BASE_WITH_PATHS as API_BASE } from '../../apiConfig';
import { useAlerts } from '../../context/AlertsContext';
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
  if ('temperature_f' in readings) {
    return { icon: Thermometer, color: 'orange' };
  }

  // Check for humidity sensors
  if ('humidity' in readings) {
    return { icon: Droplet, color: 'cyan' };
  }

  // Check for motion sensors
  if ('motion' in readings) {
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
      value: `${temp.toFixed(1)}°`,
      icon: Thermometer,
    });
  }

  // Humidity
  const humidity = readings.humidity;
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
    display.push({
      label: 'Water',
      value: !water ? 'Dry' : 'LEAK!',
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
  const [tempSparklineData, setTempSparklineData] = useState<number[]>([]);
  const [humiditySparklineData, setHumiditySparklineData] = useState<number[]>([]);
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
              // API returns newest first, reverse for sparkline (oldest to newest, left to right)
              const temps = readings
                .map((r: { value: number }) => r.value)
                .filter((v: number) => v > 0)
                .reverse();
              setTempSparklineData(temps);

              // Calculate trend: current (newest) vs previous
              if (temps.length >= 2) {
                const current = temps[temps.length - 1];
                const previous = temps[temps.length - 2];
                const delta = current - previous;
                setTempTrend({
                  current,
                  previous,
                  delta,
                  direction: Math.abs(delta) < 0.5 ? 'stable' : delta > 0 ? 'up' : 'down',
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
              // API returns newest first, reverse for sparkline (oldest to newest, left to right)
              const humidities = readings
                .map((r: { value: number }) => r.value)
                .filter((v: number) => v > 0)
                .reverse();
              setHumiditySparklineData(humidities);

              // Calculate trend: current (newest) vs previous
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

  // Use alerts context for alert state instead of device.active which may be stale
  const { hasDeviceAlert, activeIncidents } = useAlerts();
  const hasAlert = hasDeviceAlert(device.id);
  const deviceIncidents = activeIncidents.filter(i => i.device_id === device.id);
  const hasCriticalAlert = hasAlert && deviceIncidents.some(i => i.severity === 'critical' || i.severity === 'high');
  const hasWarningAlert = hasAlert && deviceIncidents.some(i => i.severity === 'medium' || i.severity === 'low');

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.5 : 1,
    cursor: editMode ? 'grab' : 'pointer',
    transition: isDragging ? undefined : 'all 0.3s ease-in-out',
    borderWidth: hasCriticalAlert ? '2px' : '1px',
    borderColor:
      hasCriticalAlert
        ? 'var(--mantine-color-red-6)'
        : hasWarningAlert
          ? 'var(--mantine-color-yellow-6)'
          : isRecentlyUpdated
            ? 'var(--mantine-color-blue-5)'
            : undefined,
    backgroundColor:
      hasCriticalAlert
        ? 'var(--mantine-color-red-0)'
        : hasWarningAlert
          ? 'var(--mantine-color-yellow-0)'
          : isRecentlyUpdated
            ? 'var(--mantine-color-blue-0)'
            : undefined,
    boxShadow:
      hasCriticalAlert
        ? '0 0 20px rgba(250, 82, 82, 0.5)'
        : hasWarningAlert
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
              color={hasCriticalAlert ? 'red' : hasWarningAlert ? 'yellow' : iconColor}
            >
              <DeviceIcon size={14} />
            </ThemeIcon>
            <div>
              <Text size="sm" fw={500}>
                {device.display_name || device.name}
              </Text>
              <Text size="sm" fw={400}>
                {device.id}
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
            {hasAlert && (
              <ThemeIcon size="xs" color={hasCriticalAlert ? 'red' : 'yellow'} variant="filled">
                <AlertTriangle size={10} />
              </ThemeIcon>
            )}
          </Group>
        </Group>

        {/* Readings row with trends - cleaner layout */}
        {displayReadings.length > 0 && (
          <Stack gap="xs" ml={editMode ? 28 : 22}>
            {displayReadings.map((reading) => {
              const ReadingIcon = reading.icon;
              const isAlert = reading.value === 'LEAK!';
              const isTemp = reading.label === 'Temp';
              const isHumidity = reading.label === 'Humidity';

              // Get trend info
              const trend = isTemp ? tempTrend : isHumidity ? humidityTrend : null;
              const sparklineData = isTemp ? tempSparklineData : isHumidity ? humiditySparklineData : [];
              const showTrend = trend && trend.delta !== undefined;

              return (
                <Group key={reading.label} gap="sm" wrap="nowrap" justify="space-between">
                  <Group gap="xs" wrap="nowrap">
                    <ReadingIcon size={12} style={{ color: isAlert ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-dimmed)' }} />
                    <Text fw={500} size="md">
                      {reading.value}
                    </Text>
                    {showTrend && trend.delta !== undefined && (
                      <Group gap={4} wrap="nowrap">
                        {trend.direction === 'up' ? (
                          <TrendingUp size={12} color="var(--mantine-color-orange-6)" />
                        ) : trend.direction === 'down' ? (
                          <TrendingDown size={12} color="var(--mantine-color-blue-6)" />
                        ) : (
                          <Minus size={12} color="var(--mantine-color-gray-6)" />
                        )}
                        <Text
                          size="xs"
                          c={trend.direction === 'up' ? 'orange' : trend.direction === 'down' ? 'blue' : 'dimmed'}
                          fw={500}
                        >
                          {isTemp
                            ? `${Math.abs(trend.delta).toFixed(1)}°`
                            : `${Math.abs(trend.delta).toFixed(0)}%`
                          }
                        </Text>
                      </Group>
                    )}
                  </Group>
                  {sparklineData.length > 2 && (
                    <Sparkline
                      data={sparklineData}
                      w={50}
                      h={16}
                      fillOpacity={0}
                      trendColors={{ positive: 'orange.6', negative: 'cyan.6', neutral: 'gray.5' }}
                      strokeWidth={2}
                      curveType="step"
                    />
                  )}
                </Group>
              );
            })}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}
