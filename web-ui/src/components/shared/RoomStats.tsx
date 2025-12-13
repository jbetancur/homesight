import { Group, Text, ThemeIcon } from '@mantine/core';
import { Thermometer, Droplet, Activity } from 'lucide-react';
import type { Device } from '../dnd/types';

interface RoomStatsProps {
  devices: Device[];
  compact?: boolean;
}

interface Stats {
  avgTemp?: number;
  avgHumidity?: number;
  activeCount: number;
  totalCount: number;
}

function calculateStats(devices: Device[]): Stats {
  const temps: number[] = [];
  const humidities: number[] = [];
  let activeCount = 0;

  devices.forEach((device) => {
    if (device.active) activeCount++;

    const temp = device.readings?.temperature_f;
    if (temp !== undefined && temp > 0) {
      temps.push(temp);
    }

    const humidity = device.readings?.humidity;
    if (humidity !== undefined && humidity > 0) {
      humidities.push(humidity);
    }
  });

  return {
    avgTemp: temps.length > 0 ? temps.reduce((a, b) => a + b, 0) / temps.length : undefined,
    avgHumidity: humidities.length > 0 ? humidities.reduce((a, b) => a + b, 0) / humidities.length : undefined,
    activeCount,
    totalCount: devices.length,
  };
}

export function RoomStats({ devices, compact = false }: RoomStatsProps) {
  const stats = calculateStats(devices);

  if (compact) {
    return (
      <Group gap="xs">
        {stats.avgTemp && (
          <Text size="xs" c="dimmed">
            {stats.avgTemp.toFixed(1)}°F
          </Text>
        )}
        {stats.avgHumidity && (
          <Text size="xs" c="dimmed">
            {stats.avgHumidity.toFixed(0)}%
          </Text>
        )}
        <Text size="xs" c="dimmed">
          {stats.activeCount > 0 ? `${stats.activeCount} active` : `${stats.totalCount} sensors`}
        </Text>
      </Group>
    );
  }

  return (
    <Group gap="md">
      {stats.avgTemp && (
        <Group gap={4}>
          <ThemeIcon size="xs" variant="light" color="orange">
            <Thermometer size={10} />
          </ThemeIcon>
          <Text size="sm" fw={500}>
            {stats.avgTemp.toFixed(1)}°F
          </Text>
        </Group>
      )}
      {stats.avgHumidity && (
        <Group gap={4}>
          <ThemeIcon size="xs" variant="light" color="cyan">
            <Droplet size={10} />
          </ThemeIcon>
          <Text size="sm" fw={500}>
            {stats.avgHumidity.toFixed(0)}%
          </Text>
        </Group>
      )}
      {stats.activeCount > 0 && (
        <Group gap={4}>
          <ThemeIcon size="xs" variant="light" color="red">
            <Activity size={10} />
          </ThemeIcon>
          <Text size="sm" fw={500}>
            {stats.activeCount}
          </Text>
        </Group>
      )}
    </Group>
  );
}
