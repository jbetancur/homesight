import { Grid, Stack, Text, Accordion, Badge, Group } from '@mantine/core';
import { Settings, Activity, Power, Gauge, AlertTriangle, Info } from 'lucide-react';
import type { DeviceEntity, EntityType } from './dnd/types';
import { EntityCard } from './EntityCard';

interface EntityGridProps {
  entities: DeviceEntity[];
  onUpdate?: () => void;
}

// Group entities by type
function groupEntitiesByType(entities: DeviceEntity[]): Record<EntityType, DeviceEntity[]> {
  const groups: Record<EntityType, DeviceEntity[]> = {
    switch: [],
    number: [],
    sensor: [],
    binary_sensor: [],
    alarm: [],
    diagnostic: [],
    config: [],
  };

  entities.forEach((entity) => {
    if (groups[entity.entity_type]) {
      groups[entity.entity_type].push(entity);
    }
  });

  return groups;
}

// Get icon for entity type
function getTypeIcon(type: EntityType, size: number = 16) {
  switch (type) {
    case 'switch':
      return <Power size={size} />;
    case 'number':
      return <Gauge size={size} />;
    case 'sensor':
      return <Activity size={size} />;
    case 'binary_sensor':
      return <Activity size={size} />;
    case 'alarm':
      return <AlertTriangle size={size} />;
    case 'diagnostic':
      return <Info size={size} />;
    case 'config':
      return <Settings size={size} />;
    default:
      return <Activity size={size} />;
  }
}

// Get human-readable label for entity type
function getTypeLabel(type: EntityType): string {
  switch (type) {
    case 'switch':
      return 'Switches';
    case 'number':
      return 'Number Controls';
    case 'sensor':
      return 'Sensors';
    case 'binary_sensor':
      return 'Binary Sensors';
    case 'alarm':
      return 'Alarms';
    case 'diagnostic':
      return 'Diagnostics';
    case 'config':
      return 'Configuration';
    default:
      return type;
  }
}

// Get description for entity type
function getTypeDescription(type: EntityType): string {
  switch (type) {
    case 'switch':
      return 'Binary controls (on/off)';
    case 'number':
      return 'Numeric configuration parameters';
    case 'sensor':
      return 'Numeric sensor readings';
    case 'binary_sensor':
      return 'Binary sensor states';
    case 'alarm':
      return 'Alarm and notification states';
    case 'diagnostic':
      return 'Device diagnostic information';
    case 'config':
      return 'Device configuration parameters';
    default:
      return '';
  }
}

export function EntityGrid({ entities, onUpdate }: EntityGridProps) {
  if (!entities || entities.length === 0) {
    return (
      <Stack align="center" p="xl">
        <Activity size={48} color="#868e96" />
        <Text size="lg" fw={600}>No Entities</Text>
        <Text size="sm" c="dimmed">This device doesn't expose any entities yet</Text>
      </Stack>
    );
  }

  const grouped = groupEntitiesByType(entities);

  // Determine which sections to show by default (controls and alarms)
  const defaultSections = ['switch', 'alarm'];

  return (
    <Stack gap="lg">
      {/* Summary */}
      <Group>
        <Text size="sm" c="dimmed">
          Total entities: <strong>{entities.length}</strong>
        </Text>
      </Group>

      {/* Accordion for different entity types */}
      <Accordion
        variant="separated"
        defaultValue={defaultSections}
        multiple
      >
        {(Object.entries(grouped) as [EntityType, DeviceEntity[]][])
          .filter(([_, items]) => items.length > 0)
          .map(([type, items]) => (
            <Accordion.Item key={type} value={type}>
              <Accordion.Control icon={getTypeIcon(type)}>
                <Group justify="space-between" pr="md">
                  <div>
                    <Text fw={600}>{getTypeLabel(type)}</Text>
                    <Text size="xs" c="dimmed">{getTypeDescription(type)}</Text>
                  </div>
                  <Badge color="blue" size="lg">
                    {items.length}
                  </Badge>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Grid>
                  {items.map((entity) => (
                    <Grid.Col key={entity.id} span={{ base: 12, sm: 6, md: 4 }}>
                      <EntityCard entity={entity} onUpdate={onUpdate} />
                    </Grid.Col>
                  ))}
                </Grid>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
      </Accordion>
    </Stack>
  );
}
