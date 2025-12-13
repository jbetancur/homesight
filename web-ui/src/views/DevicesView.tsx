
import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Badge, Loader, Stack, Title, Text, Card, Group, Paper, Button, Modal,
  ActionIcon, Tooltip, ScrollArea, TextInput, MultiSelect, Grid
} from '@mantine/core';
import {
  Wifi, Activity, Trash2, RefreshCw, FileText, Search,
  Filter, Grid3x3, List, Power, Lock, Lightbulb, Thermometer, Home, Battery,
  Droplets, Zap, ToggleLeft
} from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;

function getDeviceIcon(type: string, size: number = 20) {
  const iconMap: Record<string, any> = {
    'switch': Power,
    'light': Lightbulb,
    'sensor': Thermometer,
    'lock': Lock,
    'climate': Thermometer,
    'thermostat': Thermometer,
  };

  const Icon = iconMap[type.toLowerCase()] || Activity;
  return <Icon size={size} />;
}

function getBatteryColor(level: number): string {
  if (level <= 20) return 'red';
  if (level <= 50) return 'yellow';
  return 'green';
}

function BatteryIndicator({ level, metadata }: { level: number | undefined; metadata?: Record<string, any> }) {
  // Only show battery for battery-powered devices (not mains-powered)
  // Skip if: level is undefined/null, level is 0, or device is mains-powered (is_listening = true)
  if (level === undefined || level === null || level === 0) return null;
  if (metadata?.is_listening === 'true') return null;

  const color = getBatteryColor(level);
  return (
    <Tooltip label={`Battery: ${level}%`}>
      <Group gap={4}>
        <Battery size={14} color={color === 'red' ? '#fa5252' : color === 'yellow' ? '#fab005' : '#40c057'} />
        <Text size="xs" c={color} fw={500}>{level}%</Text>
      </Group>
    </Tooltip>
  );
}

// Format a sensor reading value for display
function formatReading(key: string, value: any): { icon: React.ReactNode; display: string; color?: string } | null {
  if (value === undefined || value === null) return null;
  
  switch (key) {
    case 'temperature_f':
      return { icon: <Thermometer size={12} />, display: `${value.toFixed ? value.toFixed(1) : value}°F` };
    case 'humidity':
      return { icon: <Droplets size={12} />, display: `${value}%` };
    case 'leak':
    case 'water':
      const isLeaking = value === true || value === 'true' || value === 1;
      return { 
        icon: <Droplets size={12} />, 
        display: isLeaking ? 'LEAK!' : 'Dry',
        color: isLeaking ? 'red' : 'green'
      };
    case 'motion':
      const hasMotion = value === true || value === 'true' || value === 1;
      return { 
        icon: <Activity size={12} />, 
        display: hasMotion ? 'Motion' : 'Clear',
        color: hasMotion ? 'orange' : 'gray'
      };
    case 'contact':
      const isOpen = value === false || value === 'false' || value === 0;
      return { 
        icon: <Activity size={12} />, 
        display: isOpen ? 'Open' : 'Closed',
        color: isOpen ? 'orange' : 'green'
      };
    case 'power':
      return { icon: <Zap size={12} />, display: `${value}W` };
    case 'energy':
      return { icon: <Zap size={12} />, display: `${value}kWh` };
    case 'brightness':
      return { icon: <Lightbulb size={12} />, display: `${value}%` };
    case 'on':
      const isOn = value === true || value === 'true' || value === 1;
      return { 
        icon: <Power size={12} />, 
        display: isOn ? 'On' : 'Off',
        color: isOn ? 'green' : 'gray'
      };
    default:
      return null;
  }
}

// Compact sensor readings display for cards and table
function SensorReadings({ readings, compact = false }: { readings?: Record<string, any>; compact?: boolean }) {
  if (!readings || Object.keys(readings).length === 0) return null;

  // Priority order for display - use standardized temperature_f (backend converts to Fahrenheit)
  const priorityKeys = ['temperature_f', 'humidity', 'leak', 'motion', 'contact', 'power', 'on', 'brightness'];
  const maxDisplay = compact ? 2 : 3;
  
  const displayReadings: Array<{ key: string; formatted: NonNullable<ReturnType<typeof formatReading>> }> = [];
  
  for (const key of priorityKeys) {
    if (displayReadings.length >= maxDisplay) break;
    if (readings[key] !== undefined) {
      const formatted = formatReading(key, readings[key]);
      if (formatted) {
        displayReadings.push({ key, formatted });
      }
    }
  }

  if (displayReadings.length === 0) return null;

  return (
    <Group gap={compact ? 6 : 8}>
      {displayReadings.map(({ key, formatted }) => (
        <Tooltip key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}>
          <Badge 
            variant="light" 
            color={formatted.color || 'blue'} 
            size={compact ? 'xs' : 'sm'}
            leftSection={formatted.icon}
          >
            {formatted.display}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  );
}

export function DevicesView() {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [offboardingId, setOffboardingId] = useState<string | null>(null);
  const [reingestingId, setReingestingId] = useState<string | null>(null);
  const [confirmModal, setConfirmModal] = useState<{open: boolean, deviceId: string | null, deviceName: string}>({
    open: false,
    deviceId: null,
    deviceName: ''
  });

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIntegrations, setSelectedIntegrations] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedRooms, setSelectedRooms] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table');

  const devicesRef = useRef<any[]>([]);

  // Initial fetch
  useEffect(() => {
    fetch(`${API_BASE}/devices`).then(res => res.json()).then(data => {
      setDevices(data || []);
      devicesRef.current = data || [];
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  // SSE event handling via callback subscription
  const handleEvent = useCallback((event: any) => {
    console.log('DevicesView received event:', event);
    let updated = devicesRef.current;
    if (event.type === "device_added") {
      const exists = updated.some(d => d.id === event.data.id);
      if (!exists) {
        updated = [...updated, event.data];
        devicesRef.current = updated;
        setDevices(updated);
      }
    } else if (event.type === "device_updated") {
      const oldDevice = updated.find(d => d.id === event.data.id);
      updated = updated.map(d => d.id === event.data.id ? event.data : d);
      devicesRef.current = updated;
      setDevices(updated);

      // Clear loading state if docs_status changed from "pending" to final state
      if (oldDevice && oldDevice.docs_status === 'pending' && event.data.docs_status !== 'pending') {
        setReingestingId(null);
      }
    } else if (event.type === "device_removed") {
      // Filter out the removed device
      updated = updated.filter(d => d.id !== event.data.id);
      devicesRef.current = updated;
      setDevices(updated);
      console.log('Device removed from list:', event.data.id, 'Remaining:', updated.length);
    }
  }, []);
  useEventSubscription(handleEvent);

  const handleOffboard = async (deviceId: string) => {
    setOffboardingId(deviceId);
    try {
      const response = await fetch(`${API_BASE}/devices/${deviceId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        // Device will be removed via SSE event
        setConfirmModal({open: false, deviceId: null, deviceName: ''});
      } else {
        alert('Failed to offboard device');
        console.error('Offboarding failed:', response.statusText);
      }
    } catch (error) {
      alert('Error offboarding device');
      console.error('Offboarding error:', error);
    } finally {
      setOffboardingId(null);
    }
  };

  const handleReingestDocs = async (deviceId: string) => {
    try {
      const response = await fetch(`${API_BASE}/devices/${deviceId}/reingest-docs`, {
        method: 'POST',
      });

      if (response.ok) {
        setReingestingId(deviceId);
      } else {
        alert('Failed to queue re-ingestion');
        console.error('Re-ingest failed:', response.statusText);
      }
    } catch (error) {
      alert('Error queuing re-ingestion');
      console.error('Re-ingest error:', error);
    }
  };

  // Get unique values for filters
  const integrations = Array.from(new Set(devices.map(d => d.integration).filter(Boolean)));
  const types = Array.from(new Set(devices.map(d => d.type).filter(Boolean)));
  const rooms = Array.from(new Set(
    devices.map(d => d.metadata?.room || d.metadata?.location).filter(Boolean)
  ));

  // Apply filters
  const filteredDevices = devices.filter(device => {
    // Search filter - search by display_name, name, alias, type, manufacturer, model
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const displayName = device.display_name || device.name;
      const matchesDisplayName = displayName?.toLowerCase().includes(query);
      const matchesName = device.name?.toLowerCase().includes(query);
      const matchesAlias = device.display_name?.toLowerCase().includes(query);
      const matchesType = device.type?.toLowerCase().includes(query);
      const matchesManufacturer = device.metadata?.manufacturer?.toLowerCase().includes(query);
      const matchesModel = device.metadata?.model?.toLowerCase().includes(query);
      if (!matchesDisplayName && !matchesName && !matchesAlias && !matchesType && !matchesManufacturer && !matchesModel) {
        return false;
      }
    }

    // Integration filter
    if (selectedIntegrations.length > 0 && !selectedIntegrations.includes(device.integration)) {
      return false;
    }

    // Type filter
    if (selectedTypes.length > 0 && !selectedTypes.includes(device.type)) {
      return false;
    }

    // Room filter
    if (selectedRooms.length > 0) {
      const room = device.metadata?.room || device.metadata?.location;
      if (!room || !selectedRooms.includes(room)) {
        return false;
      }
    }

    return true;
  });

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading devices...</Text>
      </Stack>
    );
  }

  const totalDevices = devices.length;
  const filteredCount = filteredDevices.length;

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Devices</Title>
          <Text size="sm" c="dimmed">Manage and monitor all your connected devices</Text>
        </div>
        <Button
          variant="light"
          leftSection={<Home size={16} />}
          onClick={() => navigate('/integrations')}
        >
          Manage Integrations
        </Button>
      </Group>

      {/* Stats */}
      <Grid>
        <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
          <Paper p="md" withBorder>
            <Group gap="xs">
              <Wifi size={24} color="#228be6" />
              <div>
                <Text size="xl" fw={700}>{totalDevices}</Text>
                <Text size="xs" c="dimmed">Total Devices</Text>
              </div>
            </Group>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
          <Paper p="md" withBorder>
            <Group gap="xs">
              <Activity size={24} color="#868e96" />
              <div>
                <Text size="xl" fw={700}>{integrations.length}</Text>
                <Text size="xs" c="dimmed">Integrations</Text>
              </div>
            </Group>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
          <Paper p="md" withBorder>
            <Group gap="xs">
              <Filter size={24} color="#f59f00" />
              <div>
                <Text size="xl" fw={700}>{filteredCount}</Text>
                <Text size="xs" c="dimmed">Filtered Results</Text>
              </div>
            </Group>
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Filters */}
      <Card withBorder p="md">
        <Stack gap="md">
          <Group justify="space-between" align="center">
            <Text size="sm" fw={600}>Filters</Text>
            <Group gap="xs">
              <ActionIcon
                variant={viewMode === 'table' ? 'filled' : 'light'}
                onClick={() => setViewMode('table')}
                title="Table View"
              >
                <List size={18} />
              </ActionIcon>
              <ActionIcon
                variant={viewMode === 'grid' ? 'filled' : 'light'}
                onClick={() => setViewMode('grid')}
                title="Grid View"
              >
                <Grid3x3 size={18} />
              </ActionIcon>
            </Group>
          </Group>

          <Grid>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <TextInput
                placeholder="Search devices..."
                leftSection={<Search size={16} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </Grid.Col>

            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <MultiSelect
                placeholder="Integration"
                data={integrations}
                value={selectedIntegrations}
                onChange={setSelectedIntegrations}
                clearable
              />
            </Grid.Col>

            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <MultiSelect
                placeholder="Device Type"
                data={types}
                value={selectedTypes}
                onChange={setSelectedTypes}
                clearable
              />
            </Grid.Col>

            {rooms.length > 0 && (
              <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
                <MultiSelect
                  placeholder="Room/Area"
                  data={rooms}
                  value={selectedRooms}
                  onChange={setSelectedRooms}
                  clearable
                />
              </Grid.Col>
            )}
          </Grid>

          {(searchQuery || selectedIntegrations.length > 0 || selectedTypes.length > 0 || selectedRooms.length > 0) && (
            <Button
              variant="subtle"
              size="xs"
              onClick={() => {
                setSearchQuery('');
                setSelectedIntegrations([]);
                setSelectedTypes([]);
                setSelectedRooms([]);
              }}
            >
              Clear All Filters
            </Button>
          )}
        </Stack>
      </Card>

      {/* Device List */}
      {filteredDevices.length === 0 ? (
        <Card withBorder p="xl">
          <Stack align="center" gap="md">
            <Wifi size={48} color="#868e96" />
            <div style={{ textAlign: 'center' }}>
              <Text size="lg" fw={600}>
                {devices.length === 0 ? 'No Devices' : 'No Matching Devices'}
              </Text>
              <Text size="sm" c="dimmed">
                {devices.length === 0
                  ? 'Visit the Integrations page to connect and onboard new devices'
                  : 'Try adjusting your filters'}
              </Text>
            </div>
          </Stack>
        </Card>
      ) : viewMode === 'table' ? (
        <Card withBorder p={0}>
          <ScrollArea>
            <Table highlightOnHover striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Model</Table.Th>
                  <Table.Th>ID</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Integration</Table.Th>
                  <Table.Th>Controls</Table.Th>
                  <Table.Th>Battery</Table.Th>
                  <Table.Th>Documentation</Table.Th>
                  <Table.Th style={{ textAlign: 'center' }}>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredDevices.map((device: any) => {
                  return (
                    <Table.Tr key={device.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/devices/${device.id}/overview`)}>
                      <Table.Td>
                        <Group gap="xs">
                          {getDeviceIcon(device.type, 16)}
                          <Text fw={500} style={{ color: '#228be6' }}>{device.display_name || device.name}</Text>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                          <Text fw={500}>{device.name}</Text>
                      </Table.Td>    
                      <Table.Td>
                          <Text fw={500}>{device.id}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" color="blue">{device.type}</Badge>
                      </Table.Td>
               
                      <Table.Td>
                        <Badge variant="outline">{device.integration}</Badge>
                      </Table.Td>
                      <Table.Td>
                        {device.controllable || device.metadata?.controllable === 'true' ? (
                          <Tooltip label={`Capabilities: ${device.capabilities?.join(', ') || device.metadata?.capabilities || 'switch'}`}>
                            <Group gap={4}>
                              <ToggleLeft size={16} color="#40c057" />
                              <Text size="xs" c="green" fw={500}>Controllable</Text>
                            </Group>
                          </Tooltip>
                        ) : (
                          <Text size="xs" c="dimmed">Read-only</Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <BatteryIndicator level={device.battery?.level} metadata={device.metadata} />
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label={device.docs_ingested ? `Ingested at ${new Date(device.docs_ingested_at).toLocaleString()}` : 'Awaiting documentation ingestion'}>
                          <Group gap="xs">
                            <FileText size={16} color={device.docs_ingested ? '#40c057' : '#868e96'} />
                            <Badge
                              variant="light"
                              color={
                                device.docs_status === 'success' ? 'green' :
                                device.docs_status === 'partial' ? 'blue' :
                                device.docs_status === 'error' ? 'red' :
                                'gray'
                              }
                              size="sm"
                            >
                              {device.docs_status || 'pending'}
                            </Badge>
                          </Group>
                        </Tooltip>
                      </Table.Td>
                      <Table.Td style={{ textAlign: 'center' }}>
                        <Group gap={4} justify="center" onClick={(e) => e.stopPropagation()}>
                          <Tooltip label={device.docs_status === 'pending' ? 'Ingestion in progress' : 'Re-ingest Documentation'}>
                            <ActionIcon
                              color="blue"
                              variant="subtle"
                              onClick={() => handleReingestDocs(device.id)}
                              loading={reingestingId === device.id || device.docs_status === 'pending'}
                              disabled={reingestingId === device.id || device.docs_status === 'pending'}
                            >
                              <RefreshCw size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label="Offboard Device">
                            <ActionIcon
                              color="red"
                              variant="subtle"
                              onClick={() => setConfirmModal({
                                open: true,
                                deviceId: device.id,
                                deviceName: device.display_name || device.name
                              })}
                              loading={offboardingId === device.id}
                              disabled={offboardingId === device.id}
                            >
                              <Trash2 size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>
      ) : (
        <Grid>
          {filteredDevices.map((device: any) => {
            return (
              <Grid.Col key={device.id} span={{ base: 12, xs: 6, sm: 4, md: 3 }}>
                <Card
                  withBorder
                  p="md"
                  style={{ cursor: 'pointer', height: '100%' }}
                  onClick={() => navigate(`/devices/${device.id}/overview`)}
                >
                  <Stack gap="sm">
                    <Group justify="space-between">
                      {getDeviceIcon(device.type, 24)}
                      <BatteryIndicator level={device.battery?.level} metadata={device.metadata} />
                    </Group>
                    <div>
                      <Text fw={600} lineClamp={1}>{device.display_name || device.name}</Text>
                      <Text size="xs" c="dimmed" lineClamp={1}>{device.metadata?.manufacturer || device.type}</Text>
                    </div>
                    {/* Sensor readings */}
                    {device.readings && Object.keys(device.readings).length > 0 && (
                      <SensorReadings readings={device.readings} compact />
                    )}
                    <Group gap="xs" wrap="wrap">
                      <Badge variant="light" color="blue" size="xs">{device.type}</Badge>
                      <Badge variant="outline" size="xs">{device.integration}</Badge>
                      {(device.controllable || device.metadata?.controllable === 'true') && (
                        <Badge variant="light" color="green" size="xs" leftSection={<ToggleLeft size={12} />}>
                          Controllable
                        </Badge>
                      )}
                    </Group>
                    <Group gap={4} justify="flex-end" onClick={(e) => e.stopPropagation()}>
                      <Tooltip label="Re-ingest Docs">
                        <ActionIcon
                          color="blue"
                          variant="subtle"
                          size="sm"
                          onClick={() => handleReingestDocs(device.id)}
                          loading={reingestingId === device.id}
                          disabled={reingestingId === device.id}
                        >
                          <RefreshCw size={14} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Offboard">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          size="sm"
                          onClick={() => setConfirmModal({
                            open: true,
                            deviceId: device.id,
                            deviceName: device.display_name || device.name
                          })}
                          loading={offboardingId === device.id}
                          disabled={offboardingId === device.id}
                        >
                          <Trash2 size={14} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Stack>
                </Card>
              </Grid.Col>
            );
          })}
        </Grid>
      )}

      {/* Confirmation Modal */}
      <Modal
        opened={confirmModal.open}
        onClose={() => setConfirmModal({open: false, deviceId: null, deviceName: ''})}
        title="Offboard Device"
        centered
      >
        <Stack gap="md">
          <Text>
            Are you sure you want to offboard <Text component="span" fw={600}>{confirmModal.deviceName}</Text>?
          </Text>
          <Text size="sm" c="dimmed">
            This will remove the device from monitoring. You can re-onboard it later from the Integrations page if needed.
          </Text>
          <Group justify="flex-end" gap="xs">
            <Button
              variant="subtle"
              onClick={() => setConfirmModal({open: false, deviceId: null, deviceName: ''})}
            >
              Cancel
            </Button>
            <Button
              color="red"
              onClick={() => confirmModal.deviceId && handleOffboard(confirmModal.deviceId)}
              loading={offboardingId === confirmModal.deviceId}
            >
              Offboard Device
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
