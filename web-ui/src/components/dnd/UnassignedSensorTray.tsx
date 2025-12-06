import { useDroppable } from '@dnd-kit/core';
import { Paper, Text, Group, ScrollArea, ThemeIcon, Badge } from '@mantine/core';
import { Inbox } from 'lucide-react';
import { DraggableSensor } from './DraggableSensor';
import type { Device } from './types';

interface UnassignedSensorTrayProps {
  devices: Device[];
  editMode: boolean;
  onDeviceClick: (device: Device) => void;
  isRecentlyUpdated: (lastUpdated: string | undefined) => boolean;
}

export function UnassignedSensorTray({
  devices,
  editMode,
  onDeviceClick,
  isRecentlyUpdated,
}: UnassignedSensorTrayProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: 'unassigned',
    data: { isUnassignedTray: true },
  });

  if (!editMode && devices.length === 0) {
    return null;
  }

  return (
    <Paper
      ref={setNodeRef}
      p="md"
      radius="md"
      withBorder
      style={{
        backgroundColor: isOver
          ? 'var(--mantine-color-orange-0)'
          : 'var(--mantine-color-gray-0)',
        borderColor: isOver
          ? 'var(--mantine-color-orange-5)'
          : 'var(--mantine-color-gray-4)',
        borderWidth: editMode ? '2px' : '1px',
        borderStyle: editMode ? 'dashed' : 'solid',
        transition: 'all 0.2s ease-in-out',
      }}
    >
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <ThemeIcon variant="light" color="gray" size="md">
            <Inbox size={18} />
          </ThemeIcon>
          <Text fw={600} size="sm">
            Unassigned Sensors
          </Text>
        </Group>
        <Badge variant="light" color={devices.length > 0 ? 'orange' : 'gray'}>
          {devices.length} {devices.length === 1 ? 'sensor' : 'sensors'}
        </Badge>
      </Group>

      {devices.length === 0 ? (
        <Text size="sm" c="dimmed" ta="center" py="md">
          {editMode
            ? 'Drag sensors here to unassign them from rooms'
            : 'All sensors are assigned to rooms'}
        </Text>
      ) : (
        <ScrollArea.Autosize mah={200}>
          <Group gap="xs" wrap="wrap">
            {devices.map((device) => (
              <div key={device.id} style={{ minWidth: '200px', flex: '1 1 200px', maxWidth: '300px' }}>
                <DraggableSensor
                  device={device}
                  editMode={editMode}
                  onClick={() => onDeviceClick(device)}
                  isRecentlyUpdated={isRecentlyUpdated(device.last_updated)}
                />
              </div>
            ))}
          </Group>
        </ScrollArea.Autosize>
      )}
    </Paper>
  );
}
