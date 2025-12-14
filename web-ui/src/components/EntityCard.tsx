import { useState } from 'react';
import { Card, Group, Stack, Text, Badge, Switch, NumberInput, Tooltip } from '@mantine/core';
import {
  Thermometer, Droplets, Zap, Activity, AlertTriangle, Settings,
  Power, Gauge, Clock, CheckCircle, XCircle
} from 'lucide-react';
import type { DeviceEntity } from './dnd/types';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;

interface EntityCardProps {
  entity: DeviceEntity;
  onUpdate?: () => void;
}

// Get icon based on entity category or name
function getEntityIcon(entity: DeviceEntity, size: number = 20) {
  const category = entity.category?.toLowerCase() || '';
  const name = entity.name?.toLowerCase() || '';

  if (category.includes('temperature') || name.includes('temperature')) {
    return <Thermometer size={size} color="#228be6" />;
  }
  if (category.includes('humidity') || name.includes('humidity')) {
    return <Droplets size={size} color="#4dabf7" />;
  }
  if (category.includes('power') || category.includes('energy') || name.includes('power')) {
    return <Zap size={size} color="#fab005" />;
  }
  if (category.includes('diagnostic')) {
    return <Activity size={size} color="#868e96" />;
  }
  if (category.includes('alarm') || entity.entity_type === 'alarm') {
    return <AlertTriangle size={size} color="#fa5252" />;
  }
  if (category.includes('config') || entity.entity_type === 'config') {
    return <Settings size={size} color="#868e96" />;
  }
  if (entity.entity_type === 'switch') {
    return <Power size={size} color={entity.value ? '#40c057' : '#868e96'} />;
  }
  if (entity.entity_type === 'number') {
    return <Gauge size={size} color="#228be6" />;
  }

  return <Activity size={size} color="#868e96" />;
}

// Format entity value for display
function formatValue(entity: DeviceEntity): string {
  if (entity.value === null || entity.value === undefined) {
    return '-';
  }

  // Boolean values
  if (typeof entity.value === 'boolean') {
    return entity.value ? 'Yes' : 'No';
  }

  // Numeric values
  if (typeof entity.value === 'number') {
    // Round to 2 decimal places if it's a float
    const rounded = Math.round(entity.value * 100) / 100;
    return entity.unit ? `${rounded} ${entity.unit}` : String(rounded);
  }

  return String(entity.value);
}

// Get color based on entity type and value
function getEntityColor(entity: DeviceEntity): string | undefined {
  if (entity.entity_type === 'alarm') {
    return entity.value ? 'red' : 'green';
  }
  if (entity.entity_type === 'binary_sensor') {
    if (entity.category === 'water' || entity.name.toLowerCase().includes('leak')) {
      return entity.value ? 'red' : 'green';
    }
    if (entity.name.toLowerCase().includes('tamper')) {
      return entity.value ? 'red' : 'green';
    }
  }
  return undefined;
}

export function EntityCard({ entity, onUpdate }: EntityCardProps) {
  const [loading, setLoading] = useState(false);
  const [localValue, setLocalValue] = useState(entity.value);

  const handleSwitchChange = async (value: boolean) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/devices/${entity.device_id}/set-entity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entity.id, value }),
      });

      if (response.ok) {
        setLocalValue(value);
        onUpdate?.();
      }
    } catch (error) {
      console.error('Failed to update entity:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleNumberChange = async (value: number | string) => {
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numValue)) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/devices/${entity.device_id}/set-entity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entity.id, value: numValue }),
      });

      if (response.ok) {
        setLocalValue(numValue);
        onUpdate?.();
      }
    } catch (error) {
      console.error('Failed to update entity:', error);
    } finally {
      setLoading(false);
    }
  };

  // Render switch entity (settable binary control)
  if (entity.entity_type === 'switch' && entity.settable) {
    const isOn = typeof localValue === 'boolean' ? localValue : Boolean(localValue);

    return (
      <Card withBorder p="md" bg={isOn ? 'green.0' : undefined}>
        <Group justify="space-between">
          <Group gap="sm">
            {getEntityIcon(entity, 24)}
            <div>
              <Text fw={600} size="sm">{entity.name}</Text>
              <Text size="xs" c="dimmed">{entity.category}</Text>
            </div>
          </Group>
          <Switch
            size="lg"
            checked={isOn}
            onChange={(e) => handleSwitchChange(e.currentTarget.checked)}
            disabled={loading}
          />
        </Group>
      </Card>
    );
  }

  // Render number entity (settable numeric control)
  if (entity.entity_type === 'number' && entity.settable) {
    const min = entity.metadata?.min !== undefined ? Number(entity.metadata.min) : 0;
    const max = entity.metadata?.max !== undefined ? Number(entity.metadata.max) : 100;
    const step = entity.metadata?.step !== undefined ? Number(entity.metadata.step) : 1;

    return (
      <Card withBorder p="md">
        <Stack gap="sm">
          <Group justify="space-between">
            <Group gap="sm">
              {getEntityIcon(entity, 20)}
              <div>
                <Text fw={600} size="sm">{entity.name}</Text>
                <Text size="xs" c="dimmed">{entity.category}</Text>
              </div>
            </Group>
            {entity.metadata?.read_only && (
              <Badge size="xs" color="gray">Read Only</Badge>
            )}
          </Group>
          <NumberInput
            value={typeof localValue === 'number' ? localValue : 0}
            onChange={handleNumberChange}
            min={min}
            max={max}
            step={step}
            disabled={loading}
            suffix={entity.unit ? ` ${entity.unit}` : undefined}
            size="sm"
          />
          {(entity.metadata?.description || entity.metadata?.help) && (
            <Text size="xs" c="dimmed">{entity.metadata.description || entity.metadata.help}</Text>
          )}
        </Stack>
      </Card>
    );
  }

  // Render alarm entity
  if (entity.entity_type === 'alarm') {
    const isActive = Boolean(entity.value);

    return (
      <Card withBorder p="md" bg={isActive ? 'red.0' : 'green.0'}>
        <Group justify="space-between">
          <Group gap="sm">
            {isActive ? <XCircle size={20} color="#fa5252" /> : <CheckCircle size={20} color="#40c057" />}
            <div>
              <Text fw={600} size="sm">{entity.name}</Text>
              <Text size="xs" c="dimmed">{entity.category}</Text>
            </div>
          </Group>
          <Badge color={isActive ? 'red' : 'green'} size="lg">
            {isActive ? 'ACTIVE' : 'OK'}
          </Badge>
        </Group>
      </Card>
    );
  }

  // Render binary sensor
  if (entity.entity_type === 'binary_sensor') {
    const isActive = Boolean(entity.value);
    const color = getEntityColor(entity);

    return (
      <Card withBorder p="md">
        <Group justify="space-between">
          <Group gap="sm">
            {getEntityIcon(entity, 20)}
            <div>
              <Text fw={600} size="sm">{entity.metadata.label}</Text>
              <Text size="xs" c="dimmed">{entity.name}</Text>
              {/* <Text fw={600} size="sm">{entity.property_key}</Text> */}
              <Text size="xs" c="dimmed">{entity.category}</Text>
            </div>
          </Group>
          <Badge color={color} size="md">
            {isActive ? 'Active' : 'Inactive'}
          </Badge>
        </Group>
      </Card>
    );
  }

  // Render sensor (read-only numeric or string value)
  const color = getEntityColor(entity);
  const value = formatValue(entity);

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          {getEntityIcon(entity, 20)}
          <div>
            <Text fw={600} size="sm">{entity.metadata.label}</Text>
            <Text size="xs" c="dimmed">{entity.name}</Text>
            <Text size="xs" c="dimmed">{entity.category}</Text>
          </div>
        </Group>
        <div style={{ textAlign: 'right' }}>
          <Text fw={700} size="lg" c={color}>
            {value}
          </Text>
          {entity.updated_at && (
            <Tooltip label={`Last updated: ${new Date(entity.updated_at).toLocaleString()}`}>
              <Text size="xs" c="dimmed">
                <Clock size={12} style={{ display: 'inline', marginRight: 4 }} />
                {new Date(entity.updated_at).toLocaleTimeString()}
              </Text>
            </Tooltip>
          )}
        </div>
      </Group>
    </Card>
  );
}
