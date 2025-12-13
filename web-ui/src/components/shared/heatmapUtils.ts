import type { Device } from '../dnd/types';

export interface HeatmapColor {
  background: string;
  border: string;
  label: string;
}

/**
 * Calculate average temperature for a room
 */
export function calculateRoomTemperature(devices: Device[]): number | undefined {
  const temps = devices
    .map((d) => d.readings?.temperature_f)
    .filter((t): t is number => t !== undefined && t > 0);

  if (temps.length === 0) return undefined;
  return temps.reduce((a, b) => a + b, 0) / temps.length;
}

/**
 * Get heatmap color based on temperature
 * Cool (< 65°F) = blue shades
 * Comfortable (65-75°F) = green shades
 * Warm (> 75°F) = red/orange shades
 */
export function getTemperatureHeatmapColor(temp: number | undefined): HeatmapColor {
  if (temp === undefined) {
    return {
      background: 'transparent',
      border: 'var(--mantine-color-gray-3)',
      label: 'No data',
    };
  }

  if (temp < 60) {
    return {
      background: 'var(--mantine-color-blue-0)',
      border: 'var(--mantine-color-blue-6)',
      label: 'Very cold',
    };
  }
  if (temp < 65) {
    return {
      background: 'var(--mantine-color-blue-0)',
      border: 'var(--mantine-color-blue-4)',
      label: 'Cool',
    };
  }
  if (temp < 68) {
    return {
      background: 'var(--mantine-color-green-0)',
      border: 'var(--mantine-color-green-4)',
      label: 'Comfortable',
    };
  }
  if (temp < 72) {
    return {
      background: 'var(--mantine-color-green-0)',
      border: 'var(--mantine-color-green-5)',
      label: 'Ideal',
    };
  }
  if (temp < 75) {
    return {
      background: 'var(--mantine-color-yellow-0)',
      border: 'var(--mantine-color-yellow-5)',
      label: 'Comfortable',
    };
  }
  if (temp < 78) {
    return {
      background: 'var(--mantine-color-orange-0)',
      border: 'var(--mantine-color-orange-5)',
      label: 'Warm',
    };
  }
  return {
    background: 'var(--mantine-color-red-0)',
    border: 'var(--mantine-color-red-6)',
    label: 'Hot',
  };
}
