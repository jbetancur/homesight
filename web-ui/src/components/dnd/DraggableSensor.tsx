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
} from 'lucide-react';
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
  const alias = (device.alias || '').toLowerCase();

  // Check for water/leak sensors
  if (
    'Water Alarm' in readings ||
    'water' in readings ||
    model.includes('water') ||
    model.includes('leak') ||
    name.includes('leak') ||
    alias.includes('leak') ||
    alias.includes('water')
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


export function DraggableSensor({
  device,
  editMode,
  onClick,
  isRecentlyUpdated = false,
}: DraggableSensorProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: device.id,
    data: { device },
    disabled: !editMode,
  });

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
                {device.alias || device.name}
              </Text>
              {device.metadata?.node_id && (
                <Text size="xs" c="dimmed">
                  Node {device.metadata.node_id}
                </Text>
              )}
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

        {/* Readings row */}
        {displayReadings.length > 0 && (
          <Group gap="xs" ml={editMode ? 28 : 22}>
            {displayReadings.map((reading) => {
              const ReadingIcon = reading.icon;
              const isAlert = reading.value === 'LEAK!';
              return (
                <Badge
                  key={reading.label}
                  size="sm"
                  variant="light"
                  color={isAlert ? 'red' : 'gray'}
                  leftSection={<ReadingIcon size={10} />}
                >
                  {reading.value}
                </Badge>
              );
            })}
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
