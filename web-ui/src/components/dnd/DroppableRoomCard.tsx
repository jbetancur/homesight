import { useDroppable } from '@dnd-kit/core';
import { Card, Text, Badge, Group, Stack, ThemeIcon, ActionIcon } from '@mantine/core';
import { Thermometer, Droplet, Flame, Zap, Settings } from 'lucide-react';
import { DraggableSensor } from './DraggableSensor';
import type { Device, Room } from './types';

interface DroppableRoomCardProps {
  room: Room;
  editMode: boolean;
  onDeviceClick: (device: Device) => void;
  onSettingsClick: (room: Room) => void;
  isRecentlyUpdated: (lastUpdated: string | undefined) => boolean;
}

const ZONE_ICONS: Record<string, any> = {
  'living-room': Thermometer,
  kitchen: Flame,
  bedroom: Thermometer,
  bathroom: Droplet,
  basement: Droplet,
  garage: Zap,
};

export function DroppableRoomCard({
  room,
  editMode,
  onDeviceClick,
  onSettingsClick,
  isRecentlyUpdated,
}: DroppableRoomCardProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: room.id,
    data: { room },
  });

  const hasCritical = room.devices.some((d) => d.state === 'critical' || d.active);
  const hasWarning = room.devices.some((d) => d.state === 'warning');

  const dropTargetStyle = editMode && isOver ? {
    backgroundColor: 'var(--mantine-color-blue-0)',
    borderColor: 'var(--mantine-color-blue-5)',
    boxShadow: '0 0 20px rgba(34, 139, 230, 0.3)',
  } : {};

  return (
    <Card
      ref={setNodeRef}
      shadow="sm"
      padding="lg"
      radius="md"
      withBorder
      style={{
        height: '100%',
        borderColor: hasCritical
          ? 'var(--mantine-color-red-6)'
          : hasWarning
            ? 'var(--mantine-color-yellow-6)'
            : undefined,
        borderWidth: hasCritical || (editMode && isOver) ? '2px' : '1px',
        transition: 'all 0.3s ease-in-out',
        ...dropTargetStyle,
      }}
    >
      <Card.Section withBorder inheritPadding py="xs">
        <Group justify="space-between">
          <Group>
            {ZONE_ICONS[room.id] &&
              (() => {
                const Icon = ZONE_ICONS[room.id];
                return (
                  <ThemeIcon
                    variant="light"
                    size="lg"
                    color={hasCritical ? 'red' : hasWarning ? 'yellow' : undefined}
                  >
                    <Icon size={20} />
                  </ThemeIcon>
                );
              })()}
            <Text fw={600}>{room.name}</Text>
          </Group>
          <Group gap="xs">
            <Badge
              size="sm"
              variant="light"
              color={hasCritical ? 'red' : hasWarning ? 'yellow' : undefined}
            >
              {room.devices.length} {room.devices.length === 1 ? 'device' : 'devices'}
            </Badge>
            {room.id !== 'unassigned' && (
              <ActionIcon
                variant="subtle"
                size="sm"
                onClick={() => onSettingsClick(room)}
              >
                <Settings size={16} />
              </ActionIcon>
            )}
          </Group>
        </Group>
      </Card.Section>

      <Stack gap="xs" mt="md">
        {editMode && isOver && room.devices.length === 0 && (
          <Text size="sm" c="blue" ta="center" py="md" fw={500}>
            Drop sensor here
          </Text>
        )}
        {!editMode && room.devices.length === 0 && (
          <Text size="sm" c="dimmed" ta="center" py="md">
            No devices assigned
          </Text>
        )}
        {editMode && !isOver && room.devices.length === 0 && (
          <Text size="sm" c="dimmed" ta="center" py="md" style={{ border: '2px dashed var(--mantine-color-gray-4)', borderRadius: '8px' }}>
            Drop sensors here
          </Text>
        )}
        {room.devices.map((device) => (
          <DraggableSensor
            key={device.id}
            device={device}
            editMode={editMode}
            onClick={() => onDeviceClick(device)}
            isRecentlyUpdated={isRecentlyUpdated(device.last_updated)}
          />
        ))}
      </Stack>
    </Card>
  );
}
