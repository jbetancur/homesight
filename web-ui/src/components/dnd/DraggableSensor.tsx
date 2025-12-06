import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { Paper, Group, Text, ThemeIcon } from '@mantine/core';
import {
  Thermometer,
  Droplet,
  Zap,
  Battery,
  BatteryLow,
  AlertTriangle,
  GripVertical,
} from 'lucide-react';
import type { Device } from './types';

interface DraggableSensorProps {
  device: Device;
  editMode: boolean;
  onClick?: () => void;
  isRecentlyUpdated?: boolean;
}

const DEVICE_ICONS: Record<string, any> = {
  temp: Thermometer,
  temperature: Thermometer,
  humidity: Droplet,
  leak: Droplet,
  motion: Zap,
  water_leak: Droplet,
};

const getStateColor = (state: string) => {
  switch (state) {
    case 'critical':
      return 'red';
    case 'warning':
      return 'yellow';
    case 'normal':
      return 'green';
    default:
      return 'gray';
  }
};

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

  const Icon = DEVICE_ICONS[device.type] || Zap;

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
      <Group justify="space-between">
        <Group gap="xs">
          {editMode && (
            <GripVertical
              size={14}
              style={{ color: 'var(--mantine-color-dimmed)', cursor: 'grab' }}
            />
          )}
          <ThemeIcon size="sm" variant="light" color={getStateColor(device.state)}>
            <Icon size={14} />
          </ThemeIcon>
          <Text size="sm" fw={500}>
            {device.alias ? `${device.alias} (${device.name})` : device.name}
          </Text>
        </Group>
        <Group gap="xs">
          {device.battery_level !== undefined && (
            <Group gap={2}>
              {device.battery_level < 20 ? (
                <BatteryLow size={14} color="var(--mantine-color-red-6)" />
              ) : (
                <Battery
                  size={14}
                  color={
                    device.battery_level < 40
                      ? 'var(--mantine-color-yellow-6)'
                      : 'var(--mantine-color-green-6)'
                  }
                />
              )}
              <Text
                size="xs"
                c={
                  device.battery_level < 20
                    ? 'red'
                    : device.battery_level < 40
                      ? 'yellow'
                      : 'dimmed'
                }
              >
                {device.battery_level}%
              </Text>
            </Group>
          )}
          {device.value !== null && device.value !== undefined && (
            <Text size="sm" fw={600}>
              {typeof device.value === 'boolean'
                ? device.value
                  ? 'Active'
                  : 'Inactive'
                : `${device.value}${device.unit || ''}`}
            </Text>
          )}
          {device.active && (
            <ThemeIcon size="xs" color="red" variant="filled">
              <AlertTriangle size={10} />
            </ThemeIcon>
          )}
        </Group>
      </Group>
    </Paper>
  );
}
