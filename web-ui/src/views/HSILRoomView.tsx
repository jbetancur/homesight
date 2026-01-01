import { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Grid,
  Text,
  Badge,
  Group,
  Stack,
  Paper,
  ThemeIcon,
  Modal,
  Select,
  Switch,
  Divider,
  NumberInput,
  MultiSelect,
  Tabs,
  Button,
  Tooltip,
  TextInput,
} from '@mantine/core';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import {
  Thermometer,
  Droplet,
  Brain,
  Cloud,
  Wind,
  Sunrise,
  Sunset,
  LayoutGrid,
  TrendingUp,
  Activity,
  GripVertical,
  Check,
  Flame,
} from 'lucide-react';
import {
  DroppableRoomCard,
  UnassignedSensorTray,
  DraggableSensor,
} from '../components/dnd';
import type { Device, Room, ZoneAttributes } from '../components/dnd';
import { API_BASE } from '../apiConfig';
import { useEventSubscription } from '../useEventSubscription';
import ClimateInsights from '../components/ClimateInsights';
import LearningProgressChart from '../components/LearningProgressChart';

interface ZoneAttributeOption {
  value: string;
  label: string;
}

interface ZoneAttributeField {
  name: string;
  label: string;
  type: 'select' | 'number' | 'boolean' | 'tags';
  category: string;
  options?: ZoneAttributeOption[];
  description?: string;
}

interface ZoneSchema {
  zone_types: ZoneAttributeOption[];
  attributes: ZoneAttributeField[];
}

export default function HSILRoomView() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [availableZones, setAvailableZones] = useState<any[]>([]);
  const [zoneSchema, setZoneSchema] = useState<ZoneSchema | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedZone, setSelectedZone] = useState<string>('');
  const [editingAlias, setEditingAlias] = useState<string>('');
  const [weather, setWeather] = useState<any>(null);
  const [editingZone, setEditingZone] = useState<Room | null>(null);
  const [editedAttributes, setEditedAttributes] = useState<ZoneAttributes | null>(null);
  const [activeTab, setActiveTab] = useState<string>('rooms');
  const [editMode, setEditMode] = useState(false);
  const [heatmapMode, setHeatmapMode] = useState(false);
  const [activeDevice, setActiveDevice] = useState<Device | null>(null);

  // DnD sensors with activation constraint to prevent accidental drags
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  // Helper to check if device was recently updated (within last 30 seconds)
  const isRecentlyUpdated = useCallback((lastUpdated: string | undefined) => {
    if (!lastUpdated) return false;
    const updateTime = new Date(lastUpdated).getTime();
    const now = new Date().getTime();
    const thirtySecondsAgo = now - 30 * 1000;
    return updateTime > thirtySecondsAgo;
  }, []);


  useEffect(() => {
    fetchRoomsAndDevices();
    fetchZoneSchema();
    fetchWeather();
    const weatherInterval = setInterval(fetchWeather, 900000); // 15 minutes
    return () => {
      clearInterval(weatherInterval);
    };
  }, []);


  // Real-time event handling - use events instead of polling
  const handleEvent = useCallback((event: any) => {
    if (event.type === "incident_added" ||
        event.type === "incident_removed" ||
        event.type === "incident_updated" ||
        event.type === "device_updated" ||
        event.type === "device_added" ||
        event.type === "device_removed" ||
        event.type === "zone_added" ||
        event.type === "zone_updated" ||
        event.type === "zone_removed") {
      fetchRoomsAndDevices();
    }
  }, []);

  useEventSubscription(handleEvent);

  const fetchZoneSchema = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zones/schema`);
      if (res.ok) {
        const data = await res.json();
        setZoneSchema(data);
      }
    } catch (error) {
      console.error('Failed to fetch zone schema:', error);
    }
  };

  const fetchWeather = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/weather`);
      if (res.ok) {
        const data = await res.json();
        setWeather(data);
      }
    } catch (error) {
      console.error('Failed to fetch weather:', error);
    }
  };

  const fetchRoomsAndDevices = async () => {
    try {
      const [devicesRes, zonesRes] = await Promise.all([
        fetch(`${API_BASE}/api/devices`),
        fetch(`${API_BASE}/api/zones`).catch(() => null),
      ]);

      const devices: Device[] = await devicesRes.json();

      let zones = [];
      if (zonesRes && zonesRes.ok) {
        zones = await zonesRes.json();
        // Filter out hidden zones
        const visibleZones = zones.filter((z: any) => !z.hidden);
        setAvailableZones(visibleZones);
      }

      // Group devices by room/zone
      const roomMap = new Map<string, Room>();

      // Add all available (visible) zones as rooms with attributes
      zones.filter((zone: any) => !zone.hidden).forEach((zone: any) => {
        roomMap.set(zone.id, {
          id: zone.id,
          name: zone.name,
          type: zone.type || 'unknown',
          devices: [],
          attributes: zone.attributes || {},
        });
      });

      // Add devices to their respective rooms
      devices.forEach((device: any) => {
        const zoneId = device.zone_id || 'unassigned';
        if (!roomMap.has(zoneId)) {
          roomMap.set(zoneId, {
            id: zoneId,
            name: zoneId === 'unassigned' ? 'Unassigned Devices' : zoneId,
            type: 'unknown',
            devices: [],
            attributes: {},
          });
        }
        // Extract battery level from unified contract
        const batteryLevel = device.battery?.level;

        roomMap.get(zoneId)!.devices.push({
          id: device.id,
          name: device.name,
          display_name: device.display_name,
          type: device.type,
          value: device.value,
          state: device.state || 'unknown',
          location: device.zone_id || 'unassigned',
          zone_id: device.zone_id,
          unit: device.unit,
          active: device.active || false,
          last_updated: device.last_seen || device.last_updated,
          trend: device.trend,
          battery_level: batteryLevel,
          raw_data: device.raw_data,
          readings: device.readings,
          battery: device.battery,
        });
      });

      setRooms(Array.from(roomMap.values()));
    } catch (error) {
      console.error('Failed to fetch rooms:', error);
    }
  };

  const handleSaveZone = async () => {
    if (!editingZone || !editedAttributes) return;
    
    try {
      await fetch(`${API_BASE}/api/zones/${editingZone.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: editingZone.id,
          name: editingZone.name,
          type: editingZone.type,
          attributes: editedAttributes,
        }),
      });
      fetchRoomsAndDevices();
      setEditingZone(null);
      setEditedAttributes(null);
    } catch (error) {
      console.error('Failed to save zone:', error);
    }
  };

  const handleDeviceZoneUpdate = async (deviceId: string, zoneId: string) => {
    try {
      await fetch(`${API_BASE}/api/devices/${deviceId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_id: zoneId }),
      });
      fetchRoomsAndDevices();
      setShowSettings(false);
      setSelectedDevice(null);
    } catch (error) {
      console.error('Failed to update device zone:', error);
    }
  };

  // DnD event handlers
  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event;
    const device = active.data.current?.device as Device;
    if (device) {
      setActiveDevice(device);
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDevice(null);

    if (!over) return;

    const device = active.data.current?.device as Device;
    const targetId = over.id as string;

    if (!device) return;

    // Skip if dropping on same zone
    const currentZoneId = device.zone_id || 'unassigned';
    if (currentZoneId === targetId) return;

    // Update device zone (empty string for unassigned)
    const newZoneId = targetId === 'unassigned' ? '' : targetId;

    try {
      await fetch(`${API_BASE}/api/devices/${device.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_id: newZoneId }),
      });
      fetchRoomsAndDevices();
    } catch (error) {
      console.error('Failed to update device zone:', error);
    }
  };

  // Get unassigned devices for the tray
  const unassignedRoom = rooms.find((r) => r.id === 'unassigned');
  const unassignedDevices = unassignedRoom?.devices || [];
  const assignedRooms = rooms.filter((r) => r.id !== 'unassigned');

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        {/* Header */}
        <Paper p="md" shadow="sm" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
          <Group justify="space-between" align="center">
            <Group>
              <ThemeIcon size="xl" radius="xl" variant="light" color="white">
                <Brain size={28} />
              </ThemeIcon>
              <div>
                <Text size="xl" fw={700} c="white">
                  Home Intelligence Layer
                </Text>
                <Text size="sm" c="rgba(255,255,255,0.8)">
                  AI-Powered Home Automation & Learning System
                </Text>
              </div>
            </Group>
          </Group>
        </Paper>

        {/* Weather Widget */}
        {weather && !weather.error && (
          <Paper p="md" shadow="sm" withBorder>
            <Group justify="space-between" wrap="nowrap">
              <Group>
                <ThemeIcon size="lg" variant="light" color="cyan">
                  <Cloud size={24} />
                </ThemeIcon>
                <div>
                  <Text size="lg" fw={600}>{weather.location || 'Weather'}</Text>
                  <Text size="sm" c="dimmed">{weather.weather?.description}</Text>
                </div>
              </Group>
              <Group gap="xl">
                <div>
                  <Group gap="xs">
                    <Thermometer size={18} />
                    <Text size="xl" fw={700}>{Math.round(weather.weather?.temperature || 0)}°F</Text>
                  </Group>
                  <Text size="xs" c="dimmed">Outside</Text>
                </div>
                <div>
                  <Group gap="xs">
                    <Droplet size={18} />
                    <Text fw={500}>{weather.weather?.humidity || 0}%</Text>
                  </Group>
                  <Text size="xs" c="dimmed">Humidity</Text>
                </div>
                <div>
                  <Group gap="xs">
                    <Wind size={18} />
                    <Text fw={500}>{Math.round(weather.weather?.wind_speed || 0)} mph</Text>
                  </Group>
                  <Text size="xs" c="dimmed">Wind</Text>
                </div>
                {weather.sun && (
                  <div>
                    <Group gap="xs">
                      <Sunrise size={16} />
                      <Text size="sm">{new Date(weather.sun.sunrise).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}</Text>
                    </Group>
                    <Group gap="xs">
                      <Sunset size={16} />
                      <Text size="sm">{new Date(weather.sun.sunset).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}</Text>
                    </Group>
                  </div>
                )}
                {weather.air_quality && (
                  <div>
                    <Badge
                      color={
                        weather.air_quality.aqi === 1 ? 'green' :
                        weather.air_quality.aqi === 2 ? 'lime' :
                        weather.air_quality.aqi === 3 ? 'yellow' :
                        weather.air_quality.aqi === 4 ? 'orange' : 'red'
                      }
                    >
                      AQI {weather.air_quality.aqi}
                    </Badge>
                    <Text size="xs" c="dimmed" mt="xs">
                      {weather.air_quality.aqi === 1 ? 'Good' :
                       weather.air_quality.aqi === 2 ? 'Fair' :
                       weather.air_quality.aqi === 3 ? 'Moderate' :
                       weather.air_quality.aqi === 4 ? 'Poor' : 'Very Poor'}
                    </Text>
                  </div>
                )}
              </Group>
            </Group>
          </Paper>
        )}

        {/* Tabs for different views */}
        <Tabs value={activeTab} onChange={(value) => setActiveTab(value || 'rooms')}>
          <Tabs.List>
            <Tabs.Tab value="rooms" leftSection={<LayoutGrid size={16} />}>
              Room Grid
            </Tabs.Tab>
            <Tabs.Tab value="correlation" leftSection={<TrendingUp size={16} />}>
              Climate Insights
            </Tabs.Tab>
            <Tabs.Tab value="learning" leftSection={<Activity size={16} />}>
              Learning Progress
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="rooms" pt="md">
            {/* Edit Mode & Heatmap Toggles */}
            <Group justify="space-between" mb="md">
              <Tooltip label="View temperature distribution across rooms">
                <Button
                  variant={heatmapMode ? 'filled' : 'light'}
                  color={heatmapMode ? 'orange' : 'gray'}
                  leftSection={<Flame size={16} />}
                  onClick={() => setHeatmapMode(!heatmapMode)}
                >
                  {heatmapMode ? 'Heatmap On' : 'Heatmap Mode'}
                </Button>
              </Tooltip>
              <Tooltip
                label={editMode ? 'Exit edit mode' : 'Enter edit mode to drag sensors between rooms'}
              >
                <Button
                  variant={editMode ? 'filled' : 'light'}
                  color={editMode ? 'green' : 'gray'}
                  leftSection={editMode ? <Check size={16} /> : <GripVertical size={16} />}
                  onClick={() => setEditMode(!editMode)}
                >
                  {editMode ? 'Done' : 'Edit Layout'}
                </Button>
              </Tooltip>
            </Group>

            {/* Room Grid with DnD */}
            <DndContext
              sensors={sensors}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
            >
              <Stack gap="lg">
                <Grid>
                  {assignedRooms.map((room) => (
                    <Grid.Col key={room.id} span={{ base: 12, sm: 6, md: 4 }}>
                      <DroppableRoomCard
                        room={room}
                        editMode={editMode}
                        heatmapMode={heatmapMode}
                        onDeviceClick={(device) => {
                          setSelectedDevice(device);
                          setSelectedZone(device.zone_id || '');
                          setEditingAlias(device.display_name || '');
                          setShowSettings(true);
                        }}
                        onSettingsClick={(room) => {
                          setEditingZone(room);
                          setEditedAttributes(room.attributes || {});
                        }}
                        isRecentlyUpdated={isRecentlyUpdated}
                      />
                    </Grid.Col>
                  ))}
                </Grid>

                {/* Unassigned Sensor Tray */}
                <UnassignedSensorTray
                  devices={unassignedDevices}
                  editMode={editMode}
                  onDeviceClick={(device) => {
                    setSelectedDevice(device);
                    setSelectedZone(device.zone_id || '');
                    setEditingAlias(device.display_name || '');
                    setShowSettings(true);
                  }}
                  isRecentlyUpdated={isRecentlyUpdated}
                />
              </Stack>

              {/* Drag Overlay - shows ghost of dragged item */}
              <DragOverlay>
                {activeDevice && (
                  <DraggableSensor
                    device={activeDevice}
                    editMode={true}
                    isRecentlyUpdated={false}
                  />
                )}
              </DragOverlay>
            </DndContext>
          </Tabs.Panel>

          <Tabs.Panel value="correlation" pt="md">
            <ClimateInsights />
          </Tabs.Panel>

          <Tabs.Panel value="learning" pt="md">
            <LearningProgressChart />
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Device Settings Modal */}
      <Modal
        opened={showSettings && selectedDevice !== null}
        onClose={() => {
          setShowSettings(false);
          setSelectedDevice(null);
          setSelectedZone('');
          setEditingAlias('');
        }}
        title={`Configure: ${selectedDevice?.display_name ? `${selectedDevice.display_name} (${selectedDevice.name})` : selectedDevice?.name}`}
      >
        <Stack gap="md">
          <TextInput
            label="Device Display Name"
            placeholder="Enter a friendly name (optional)"
            value={editingAlias}
            onChange={(e) => setEditingAlias(e.currentTarget.value)}
            description="Leave empty to use the default device name"
          />
          <Select
            label="Assign to Room"
            placeholder="Select a room"
            data={availableZones.map((zone: any) => ({ value: zone.id, label: zone.name }))}
            value={selectedZone}
            onChange={(value) => setSelectedZone(value || '')}
          />
          <Group justify="flex-end" gap="sm">
            <Button
              variant="subtle"
              onClick={() => {
                setShowSettings(false);
                setSelectedDevice(null);
                setSelectedZone('');
                setEditingAlias('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={async () => {
                if (!selectedDevice) return;
                
                try {
                  // Update alias if changed
                  if (editingAlias !== (selectedDevice.display_name || '')) {
                    const aliasResponse = await fetch(`${API_BASE}/api/devices/${selectedDevice.id}`, {
                      method: 'PATCH',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ display_name: editingAlias.trim() || null }),
                    });
                    if (!aliasResponse.ok) {
                      console.error('Failed to update display name');
                    }
                  }
                  
                  // Update zone if changed
                  if (selectedZone && selectedZone !== selectedDevice.zone_id) {
                    await handleDeviceZoneUpdate(selectedDevice.id, selectedZone);
                  } else {
                    // If only alias changed, refresh the data
                    fetchRoomsAndDevices();
                    setShowSettings(false);
                    setSelectedDevice(null);
                    setSelectedZone('');
                    setEditingAlias('');
                  }
                } catch (error) {
                  console.error('Error updating device:', error);
                }
              }}
            >
              Save
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Zone Attributes Modal */}
      <Modal
        opened={editingZone !== null}
        onClose={() => {
          setEditingZone(null);
          setEditedAttributes(null);
        }}
        title={`Configure Zone: ${editingZone?.name}`}
        size="lg"
      >
        {editedAttributes && zoneSchema && (
          <Stack gap="md">
            {/* Render attributes by category */}
            {['basic', 'hvac', 'plumbing', 'safety', 'custom'].map((category, catIdx) => {
              const categoryLabels: Record<string, string> = {
                basic: 'Basic Properties',
                hvac: 'HVAC & Climate',
                plumbing: 'Plumbing & Water',
                safety: 'Safety & Occupancy',
                custom: 'Custom',
              };
              const categoryFields = zoneSchema.attributes.filter(f => f.category === category);
              if (categoryFields.length === 0) return null;

              return (
                <div key={category}>
                  {catIdx > 0 && <Divider />}
                  <Text fw={600} size="sm" c="dimmed">{categoryLabels[category]}</Text>
                  
                  {/* Special handling for basic category with floor type and square feet */}
                  {category === 'basic' && (
                    <Group grow>
                      {categoryFields
                        .filter(f => f.type === 'select' || f.type === 'number')
                        .map(field => (
                          field.type === 'select' ? (
                            <Select
                              key={field.name}
                              label={field.label}
                              placeholder={`Select ${field.label.toLowerCase()}`}
                              data={field.options?.map(o => ({ value: o.value, label: o.label })) || []}
                              value={(editedAttributes[field.name] as string) || ''}
                              onChange={(value) => setEditedAttributes({ ...editedAttributes, [field.name]: value || undefined })}
                            />
                          ) : (
                            <NumberInput
                              key={field.name}
                              label={field.label}
                              placeholder={field.description || field.label}
                              value={(editedAttributes[field.name] as number) || ''}
                              onChange={(value) => setEditedAttributes({ ...editedAttributes, [field.name]: typeof value === 'number' ? value : undefined })}
                              min={0}
                            />
                          )
                        ))}
                    </Group>
                  )}

                  {/* Boolean switches */}
                  <Group>
                    {categoryFields
                      .filter(f => f.type === 'boolean')
                      .map(field => (
                        <Switch
                          key={field.name}
                          label={field.label}
                          checked={(editedAttributes[field.name] as boolean) || false}
                          onChange={(e) => setEditedAttributes({ ...editedAttributes, [field.name]: e.currentTarget.checked })}
                        />
                      ))}
                  </Group>

                  {/* Tags */}
                  {categoryFields
                    .filter(f => f.type === 'tags')
                    .map(field => {
                      const tags = editedAttributes.tags;
                      const tagArray = Array.isArray(tags) ? tags : [];
                      return (
                        <MultiSelect
                          key={field.name}
                          label={field.label}
                          placeholder={field.description || `Add ${field.label.toLowerCase()}`}
                          data={tagArray}
                          value={tagArray}
                          onChange={(value) => setEditedAttributes({ ...editedAttributes, tags: value })}
                          searchable
                        />
                      );
                    })}
                </div>
              );
            })}

            <Group justify="flex-end" gap="sm" mt="md">
              <Button
                variant="subtle"
                onClick={() => {
                  setEditingZone(null);
                  setEditedAttributes(null);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSaveZone}
              >
                Save Zone
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
