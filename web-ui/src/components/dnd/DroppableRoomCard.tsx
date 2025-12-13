import { useDroppable } from '@dnd-kit/core';
import { Card, Text, Badge, Group, Stack, ActionIcon } from '@mantine/core';
import { Settings } from 'lucide-react';
import { DraggableSensor } from './DraggableSensor';
import { RoomStats, calculateRoomTemperature, getTemperatureHeatmapColor } from '../shared';
import type { Device, Room } from './types';

interface DroppableRoomCardProps {
  room: Room;
  editMode: boolean;
  onDeviceClick: (device: Device) => void;
  onSettingsClick: (room: Room) => void;
  isRecentlyUpdated: (lastUpdated: string | undefined) => boolean;
  heatmapMode?: boolean;
}

export function DroppableRoomCard({
  room,
  editMode,
  onDeviceClick,
  onSettingsClick,
  isRecentlyUpdated,
  heatmapMode = false,
}: DroppableRoomCardProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: room.id,
    data: { room },
  });

  const hasCritical = room.devices.some((d) => d.state === 'critical' || d.active);
  const hasWarning = room.devices.some((d) => d.state === 'warning');

  // Heatmap coloring
  const roomTemp = calculateRoomTemperature(room.devices);
  const heatmapColor = getTemperatureHeatmapColor(roomTemp);

  const dropTargetStyle = editMode && isOver ? {
    backgroundColor: 'var(--mantine-color-blue-0)',
    borderColor: 'var(--mantine-color-blue-5)',
    boxShadow: '0 0 20px rgba(34, 139, 230, 0.3)',
  } : {};

  const heatmapStyle = heatmapMode ? {
    backgroundColor: heatmapColor.background,
    borderColor: heatmapColor.border,
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
            : heatmapMode
              ? heatmapColor.border
              : undefined,
        borderWidth: hasCritical || (editMode && isOver) || heatmapMode ? '2px' : '1px',
        transition: 'all 0.3s ease-in-out',
        ...dropTargetStyle,
        ...heatmapStyle,
      }}
    >
      <Card.Section withBorder inheritPadding py="xs">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={600}>{room.name}</Text>
            {room.devices.length > 0 && <RoomStats devices={room.devices} compact />}
          </div>
          <Group gap="xs">
            {heatmapMode && roomTemp && (
              <Badge size="sm" variant="light" color="gray">
                {heatmapColor.label}
              </Badge>
            )}
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
