import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Stack, Title, Text, Card, Group, Badge, Loader, Button, Table, Paper, Tabs,
  Grid, ActionIcon, Tooltip, Progress
} from '@mantine/core';
import {
  ArrowLeft, FileText, Activity, Droplets, Thermometer, Info, Clock, RefreshCw,
  AlertCircle, CheckCircle, Battery, Zap, Power, Wind, Eye
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useEventSubscription } from '../useEventSubscription';
import { API_BASE_WITH_PATHS } from '../apiConfig';
import { CapabilityWidget } from '../components/DeviceCapabilityWidgets';

const API_BASE = API_BASE_WITH_PATHS;

interface Sensor {
  id: string;
  device_id: string;
  name: string;
  type: string;
  unit: string;
  metadata: Record<string, string>;
  created_at: string;
  updated_at: string;
}

interface Device {
  id: string;
  name: string;
  type: string;
  integration: string;
  metadata: Record<string, any>;
  capabilities?: string[];
  state?: Record<string, any>;
  readings?: Record<string, any>;
  battery_level?: number;
  battery_low?: boolean;
  docs_ingested: boolean;
  docs_ingested_at: string;
  docs_status: string;
  last_seen: string;
  created_at: string;
  updated_at: string;
}

interface KnowledgeBase {
  device_id: string;
  device_name: string;
  search_query: string;
  docs_status: string;
  docs_ingested: boolean;
  ingested_at?: string;
  articles: Array<{
    title: string;
    type: string;
    source: string;
    description: string;
    available: boolean;
  }>;
}

function getSensorIcon(type: string) {
  switch (type?.toLowerCase()) {
    case 'humidity':
      return <Droplets size={16} />;
    case 'temperature':
      return <Thermometer size={16} />;
    default:
      return <Activity size={16} />;
  }
}

function getBatteryColor(level: number): string {
  if (level <= 20) return 'red';
  if (level <= 50) return 'yellow';
  return 'green';
}

// Keys to skip in readings display (internal Z-Wave values, redundant readings)
const HIDDEN_READING_KEYS = new Set([
  'alarmLevel',
  'alarmType', 
  'Water Alarm',  // Redundant with 'water'
  'Alarm Level',
  'Alarm Type',
]);

// Normalize reading key for consistent display
function normalizeReadingKey(key: string): string {
  const normalized = key.toLowerCase().replace(/\s+/g, '_');
  // Map variations to canonical names
  const keyMap: Record<string, string> = {
    'water_alarm': 'water',
    'water_leak': 'water',
  };
  return keyMap[normalized] || normalized;
}

// Format sensor reading for display with icon and color
function formatSensorReading(key: string, value: any): { icon: React.ReactNode; display: string; color?: string; label: string } | null {
  if (value === undefined || value === null) return null;
  
  // Skip hidden/internal readings
  if (HIDDEN_READING_KEYS.has(key)) return null;
  
  const normalizedKey = normalizeReadingKey(key);
  
  switch (normalizedKey) {
    case 'temperature':
      return { icon: <Thermometer size={20} color="#228be6" />, display: `${value}°`, label: 'Temperature' };
    case 'humidity':
      return { icon: <Droplets size={20} color="#228be6" />, display: `${value}%`, label: 'Humidity' };
    case 'leak':
    case 'water': {
      const isLeaking = value === true || value === 'true' || value === 1 || value === 2 || value === 255;
      return { 
        icon: <Droplets size={20} color={isLeaking ? '#fa5252' : '#40c057'} />, 
        display: isLeaking ? 'LEAK DETECTED!' : 'Dry',
        color: isLeaking ? 'red' : 'green',
        label: 'Water Status'
      };
    }
    case 'motion': {
      const hasMotion = value === true || value === 'true' || value === 1;
      return { 
        icon: <Eye size={20} color={hasMotion ? '#fd7e14' : '#868e96'} />, 
        display: hasMotion ? 'Motion Detected' : 'No Motion',
        color: hasMotion ? 'orange' : 'gray',
        label: 'Motion'
      };
    }
    case 'contact': {
      const isOpen = value === false || value === 'false' || value === 0;
      return { 
        icon: <Activity size={20} color={isOpen ? '#fd7e14' : '#40c057'} />, 
        display: isOpen ? 'Open' : 'Closed',
        color: isOpen ? 'orange' : 'green',
        label: 'Contact'
      };
    }
    case 'tamper': {
      const isTampered = value === true || value === 'true' || value === 1;
      return { 
        icon: <AlertCircle size={20} color={isTampered ? '#fa5252' : '#40c057'} />, 
        display: isTampered ? 'TAMPER!' : 'OK',
        color: isTampered ? 'red' : 'green',
        label: 'Tamper'
      };
    }
    case 'power':
      return { icon: <Zap size={20} color="#fab005" />, display: `${value} W`, label: 'Power' };
    case 'energy':
      return { icon: <Zap size={20} color="#fab005" />, display: `${value} kWh`, label: 'Energy' };
    case 'brightness':
      return { icon: <Power size={20} color="#fab005" />, display: `${value}%`, label: 'Brightness' };
    case 'on': {
      const isOn = value === true || value === 'true' || value === 1;
      return { 
        icon: <Power size={20} color={isOn ? '#40c057' : '#868e96'} />, 
        display: isOn ? 'On' : 'Off',
        color: isOn ? 'green' : 'gray',
        label: 'Power'
      };
    }
    default:
      // Generic display for unknown readings - use formatted key as label
      return { 
        icon: <Activity size={20} color="#868e96" />, 
        display: String(value),
        label: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      };
  }
}

function getDeviceStatus(lastSeen: string) {
  const lastSeenDate = new Date(lastSeen);
  const now = new Date();
  const diffMinutes = (now.getTime() - lastSeenDate.getTime()) / (1000 * 60);

  if (diffMinutes < 5) {
    return { label: 'Online', color: 'green' };
  } else if (diffMinutes < 30) {
    return { label: 'Recent', color: 'yellow' };
  } else {
    return { label: 'Offline', color: 'red' };
  }
}

export function DeviceOverviewView() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<Device | null>(null);
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const deviceRef = useRef<Device | null>(null);
  const incidentsRef = useRef<any[]>([]);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        if (!deviceId) {
          setError('Device ID not found');
          return;
        }

        // Fetch device
        const deviceRes = await fetch(`${API_BASE}/devices/${deviceId}`);
        if (!deviceRes.ok) throw new Error('Failed to fetch device');
        const deviceData = await deviceRes.json();
        setDevice(deviceData);
        deviceRef.current = deviceData;

        // Fetch knowledge base
        try {
          const kbRes = await fetch(`${API_BASE}/devices/${deviceId}/knowledge-base`);
          if (kbRes.ok) {
            setKnowledgeBase(await kbRes.json());
          }
        } catch (e) {
          console.log('Knowledge base not available:', e);
        }

        // Fetch sensors - try the new endpoint first, fall back to mock data
        try {
          const sensorsRes = await fetch(`${API_BASE}/devices/${deviceId}/sensors`);
          if (sensorsRes.ok) {
            setSensors(await sensorsRes.json());
          } else {
            // Fallback: create mock sensors based on device type
            setSensors(createMockSensors(deviceId));
          }
        } catch {
          // If endpoint doesn't exist yet, create mock sensors
          setSensors(createMockSensors(deviceId));
        }

        // Fetch incidents for this device
        try {
          const incidentsRes = await fetch(`${API_BASE}/devices/${deviceId}/incidents`);
          if (incidentsRes.ok) {
            const incidentData = await incidentsRes.json();
            setIncidents(incidentData || []);
            incidentsRef.current = incidentData || [];
          }
        } catch (e) {
          console.log('Incidents not available:', e);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [deviceId]);

  // SSE event handling for real-time device and incident updates
  const handleEvent = useCallback((event: any) => {
    console.log('DeviceOverviewView received event:', event);
    if (event.type === "device_updated") {
      // Only update if it's the device we're currently viewing
      if (event.data.id === deviceId) {
        console.log('Updating device from SSE event:', event.data);

        // Check if docs_status changed before updating
        const docsStatusChanged = deviceRef.current && event.data.docs_status !== deviceRef.current.docs_status;

        setDevice(event.data);
        deviceRef.current = event.data;

        // If docs_status changed, refresh knowledge base
        if (docsStatusChanged) {
          console.log('Docs status changed, refreshing knowledge base');
          fetch(`${API_BASE}/devices/${deviceId}/knowledge-base`)
            .then(res => res.ok ? res.json() : null)
            .then(kb => {
              if (kb) setKnowledgeBase(kb);
            })
            .catch(err => console.error('Failed to refresh knowledge base:', err));
        }
      }
    } else if (event.type === "incident_added") {
      // Add incident if it's for this device
      if (event.data.device_id === deviceId) {
        const exists = incidentsRef.current.some(i => i.id === event.data.id);
        if (!exists) {
          const updated = [...incidentsRef.current, event.data];
          setIncidents(updated);
          incidentsRef.current = updated;
        }
      }
    } else if (event.type === "incident_updated") {
      // Update incident if it's for this device
      if (event.data.device_id === deviceId) {
        const updated = incidentsRef.current.map(i =>
          i.id === event.data.id ? event.data : i
        );
        setIncidents(updated);
        incidentsRef.current = updated;
      }
    } else if (event.type === "incident_removed") {
      // Remove incident
      const updated = incidentsRef.current.filter(i => i.id !== event.data.id);
      setIncidents(updated);
      incidentsRef.current = updated;
    }
  }, [deviceId]);
  useEventSubscription(handleEvent);

  function createMockSensors(devId: string): Sensor[] {
    const mockSensors: Record<string, Sensor[]> = {
      'temp_sensor': [
        {
          id: `${devId}-temp`,
          device_id: devId,
          name: 'Temperature',
          type: 'temperature',
          unit: '°C',
          metadata: { min: '-10', max: '50', accuracy: '±0.5' },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      'humidity_sensor': [
        {
          id: `${devId}-humidity`,
          device_id: devId,
          name: 'Humidity',
          type: 'humidity',
          unit: '%',
          metadata: { min: '0', max: '100', accuracy: '±3' },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      'leak_sensor': [
        {
          id: `${devId}-leak`,
          device_id: devId,
          name: 'Leak Detection',
          type: 'leak',
          unit: 'Status',
          metadata: { values: 'Dry, Wet' },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    };
    return mockSensors[device?.type || 'temp_sensor'] || [];
  }

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading device details...</Text>
      </Stack>
    );
  }

  if (error || !device) {
    return (
      <Stack gap="md">
        <Button
          variant="subtle"
          leftSection={<ArrowLeft size={18} />}
          onClick={() => navigate('/')}
        >
          Back to Devices
        </Button>
        <Card withBorder p="xl">
          <Stack align="center" gap="md">
            <Text size="lg" fw={600}>Error Loading Device</Text>
            <Text size="sm" c="dimmed">{error || 'Device not found'}</Text>
          </Stack>
        </Card>
      </Stack>
    );
  }

  const status = getDeviceStatus(device.last_seen);
  const capabilities = device.capabilities || device.metadata?.capabilities || [];

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const deviceRes = await fetch(`${API_BASE}/devices/${deviceId}`);
      if (deviceRes.ok) {
        const deviceData = await deviceRes.json();
        setDevice(deviceData);
        deviceRef.current = deviceData;
      }
    } catch (error) {
      console.error('Failed to refresh device:', error);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between" align="center">
        <Button
          variant="subtle"
          leftSection={<ArrowLeft size={18} />}
          onClick={() => navigate('/')}
        >
          Back to Devices
        </Button>
        <Tooltip label="Refresh device data">
          <ActionIcon
            variant="light"
            onClick={handleRefresh}
            loading={refreshing}
            size="lg"
          >
            <RefreshCw size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {/* Device Header Card */}
      <Card withBorder p="lg">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <div>
              <Group gap="sm" mb="xs">
                <Title order={2}>{device.name}</Title>
                <Badge color={status.color}>{status.label}</Badge>
              </Group>
              <Group gap="sm">
                <Badge variant="light" color="blue">{device.type}</Badge>
                <Badge variant="outline">{device.integration}</Badge>
              </Group>
            </div>
          </Group>

          <Grid>
            <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
              <Paper p="sm" withBorder>
                <Group gap="xs">
                  <Info size={16} color="#868e96" />
                  <div>
                    <Text size="xs" c="dimmed">Manufacturer</Text>
                    <Text size="sm" fw={500}>{device.metadata?.manufacturer || '-'}</Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
              <Paper p="sm" withBorder>
                <Group gap="xs">
                  <Info size={16} color="#868e96" />
                  <div>
                    <Text size="xs" c="dimmed">Model</Text>
                    <Text size="sm" fw={500}>{device.metadata?.model || '-'}</Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
              <Paper p="sm" withBorder>
                <Group gap="xs">
                  <Clock size={16} color="#868e96" />
                  <div>
                    <Text size="xs" c="dimmed">Last Seen</Text>
                    <Text size="sm" fw={500}>
                      {new Date(device.last_seen).toLocaleString()}
                    </Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, xs: 6, sm: 3 }}>
              <Paper p="sm" withBorder>
                <Group gap="xs">
                  <Activity size={16} color="#868e96" />
                  <div>
                    <Text size="xs" c="dimmed">Capabilities</Text>
                    <Text size="sm" fw={500}>{capabilities.length || 0}</Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>
          </Grid>
        </Stack>
      </Card>

      {/* Current Readings - Always visible at the top */}
      {((device.readings && Object.keys(device.readings).length > 0) || device.battery_level !== undefined) && (
        <Card withBorder p="lg">
          <Stack gap="md">
            <Text fw={600} size="lg">Current Readings</Text>
            <Grid>
              {/* Battery Status */}
              {device.battery_level !== undefined && (
                <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
                  <Paper p="md" withBorder bg={device.battery_low ? 'red.0' : 'green.0'} radius="md">
                    <Group justify="space-between">
                      <Group gap="sm">
                        <Battery size={24} color={device.battery_low ? '#fa5252' : '#40c057'} />
                        <div>
                          <Text size="xs" c="dimmed">Battery</Text>
                          <Text fw={600} size="lg" c={getBatteryColor(device.battery_level)}>
                            {device.battery_level}%
                          </Text>
                        </div>
                      </Group>
                      <Progress 
                        value={device.battery_level} 
                        size="xl" 
                        w={60}
                        color={getBatteryColor(device.battery_level)}
                      />
                    </Group>
                  </Paper>
                </Grid.Col>
              )}
              {/* Sensor Readings */}
              {device.readings && Object.entries(device.readings).map(([key, value]) => {
                const reading = formatSensorReading(key, value);
                if (!reading) return null;
                return (
                  <Grid.Col key={key} span={{ base: 6, sm: 4, md: 3 }}>
                    <Paper p="md" bg="gray.0" radius="md" withBorder>
                      <Group gap="xs">
                        {reading.icon}
                        <div>
                          <Text size="xs" c="dimmed">{reading.label}</Text>
                          <Text fw={600} c={reading.color || 'dark'} size="lg">
                            {reading.display}
                          </Text>
                        </div>
                      </Group>
                    </Paper>
                  </Grid.Col>
                );
              })}
            </Grid>
          </Stack>
        </Card>
      )}

      {/* Device Details Grid */}
      <Tabs defaultValue="controls">
        <Tabs.List>
          <Tabs.Tab value="controls">Controls</Tabs.Tab>
          <Tabs.Tab value="sensors">Sensors</Tabs.Tab>
          <Tabs.Tab value="incidents">
            Incidents
            {incidents.filter(i => i.status !== 'resolved').length > 0 && (
              <Badge size="sm" color="red" ml={5}>
                {incidents.filter(i => i.status !== 'resolved').length}
              </Badge>
            )}
          </Tabs.Tab>
          <Tabs.Tab value="info">Device Information</Tabs.Tab>
          <Tabs.Tab value="docs">Documentation</Tabs.Tab>
        </Tabs.List>

        {/* Controls Tab - Capability-driven widgets */}
        <Tabs.Panel value="controls" pt="md">
          {(!device.capabilities || device.capabilities.length === 0) ? (
            <Card withBorder p="xl">
              <Stack align="center" gap="md">
                <Activity size={48} color="#868e96" />
                <div style={{ textAlign: 'center' }}>
                  <Text size="lg" fw={600}>No Controls Available</Text>
                  <Text size="sm" c="dimmed">
                    This device hasn't reported any controllable capabilities yet
                  </Text>
                </div>
              </Stack>
            </Card>
          ) : (
            <Grid>
              {device.capabilities.map((capability: string, idx: number) => (
                <Grid.Col key={idx} span={{ base: 12, sm: 6, md: 4 }}>
                  <CapabilityWidget
                    deviceId={device.id}
                    capability={capability}
                    state={device.state}
                    metadata={device.metadata}
                  />
                </Grid.Col>
              ))}
            </Grid>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="sensors" pt="md">
          <Stack gap="md">
            {/* Sensor Details Table */}
            {sensors.length === 0 ? (
              <Card withBorder p="xl">
                <Stack align="center" gap="md">
                  <Activity size={48} color="#868e96" />
                  <div style={{ textAlign: 'center' }}>
                    <Text size="lg" fw={600}>No Sensor Details</Text>
                    <Text size="sm" c="dimmed">This device hasn't reported detailed sensor metadata yet</Text>
                  </div>
                </Stack>
              </Card>
            ) : (
              <Card withBorder p={0}>
                  <Table highlightOnHover striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Sensor Name</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Unit</Table.Th>
                        <Table.Th>Created</Table.Th>
                        <Table.Th style={{ textAlign: 'center' }}>Action</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {sensors.map((sensor) => (
                        <Table.Tr key={sensor.id}>
                          <Table.Td>
                            <Group gap="xs">
                              {getSensorIcon(sensor.type)}
                              <Text fw={500}>{sensor.name}</Text>
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <Badge variant="light" size="sm">
                              {sensor.type}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm">{sensor.unit}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm" c="dimmed">
                              {new Date(sensor.created_at).toLocaleDateString()}
                            </Text>
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'center' }}>
                            <Button
                              size="xs"
                              variant="light"
                              onClick={() =>
                                navigate(`/devices/${deviceId}/sensors/${sensor.id}`)
                              }
                            >
                              View Details
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Card>
            )}
          </Stack>
        </Tabs.Panel>

        {/* Incidents Tab */}
        <Tabs.Panel value="incidents" pt="md">
          <Stack gap="md">
            {incidents.length === 0 ? (
              <Card withBorder p="xl">
                <Stack align="center" gap="md">
                  <CheckCircle size={48} color="#40c057" />
                  <div style={{ textAlign: 'center' }}>
                    <Text size="lg" fw={600}>No Incidents</Text>
                    <Text size="sm" c="dimmed">This device has no recorded incidents</Text>
                  </div>
                </Stack>
              </Card>
            ) : (
              <>
                {incidents.filter(i => i.status !== 'resolved').length > 0 && (
                  <>
                    <Title order={5} c="red">Active Incidents</Title>
                    <Stack gap="sm">
                      {incidents.filter(i => i.status !== 'resolved').map((incident: any) => (
                        <Card key={incident.id} withBorder padding="md" shadow="sm">
                          <Stack gap="xs">
                            <Group justify="space-between">
                              <Group gap="xs">
                                <AlertCircle size={18} color="#fa5252" />
                                <Text fw={600}>{incident.title}</Text>
                              </Group>
                              <Group gap="xs">
                                <Badge color={incident.severity === 'critical' ? 'red' : incident.severity === 'high' ? 'orange' : 'yellow'}>
                                  {incident.severity}
                                </Badge>
                                {incident.type && (
                                  <Badge color="grape" variant="dot">
                                    {incident.type.replace(/_/g, ' ')}
                                  </Badge>
                                )}
                              </Group>
                            </Group>
                            <Text size="sm">{incident.description}</Text>
                            <Text size="xs" c="dimmed">
                              Started: {new Date(incident.created_at).toLocaleString()}
                            </Text>
                          </Stack>
                        </Card>
                      ))}
                    </Stack>
                  </>
                )}
                {incidents.filter(i => i.status === 'resolved').length > 0 && (
                  <>
                    <Title order={5} c="green" mt="md">Resolved Incidents</Title>
                    <Stack gap="sm">
                      {incidents.filter(i => i.status === 'resolved').map((incident: any) => (
                        <Card key={incident.id} withBorder padding="md" opacity={0.7}>
                          <Stack gap="xs">
                            <Group justify="space-between">
                              <Group gap="xs">
                                <CheckCircle size={18} color="#40c057" />
                                <Text fw={600}>{incident.title}</Text>
                              </Group>
                              <Group gap="xs">
                                <Badge color="green">resolved</Badge>
                                {incident.type && (
                                  <Badge color="grape" variant="dot">
                                    {incident.type.replace(/_/g, ' ')}
                                  </Badge>
                                )}
                              </Group>
                            </Group>
                            <Text size="sm">{incident.description}</Text>
                            <Text size="xs" c="dimmed">
                              Resolved: {incident.resolved_at ? new Date(incident.resolved_at).toLocaleString() : 'Unknown'}
                            </Text>
                          </Stack>
                        </Card>
                      ))}
                    </Stack>
                  </>
                )}
              </>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="info" pt="md">
          <Stack gap="md">
            <Group>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Device ID</Text>
                <Text fw={500} size="sm" style={{ wordBreak: 'break-all' }}>
                  {device.id}
                </Text>
              </div>
            </Group>
            <Group>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Type</Text>
                <Text fw={500}>{device.type}</Text>
              </div>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Integration</Text>
                <Badge variant="outline">{device.integration}</Badge>
              </div>
            </Group>
            <Group>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Manufacturer</Text>
                <Text fw={500}>{device.metadata?.manufacturer || '-'}</Text>
              </div>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Model</Text>
                <Text fw={500}>{device.metadata?.model || '-'}</Text>
              </div>
            </Group>
            {Object.keys(device.metadata || {}).length > 0 && (
              <div>
                <Text size="sm" c="dimmed" mb="xs">
                  Additional Metadata
                </Text>
                <Stack gap="xs">
                  {Object.entries(device.metadata)
                    .filter(([key]) => key !== 'manufacturer' && key !== 'model' && key !== 'battery_level' && key !== 'battery_low')
                    .map(([key, value]) => (
                      <Group key={key} justify="space-between">
                        <Text size="sm" c="dimmed">
                          {key.replace(/_/g, ' ')}
                        </Text>
                        <Text size="sm">{String(value)}</Text>
                      </Group>
                    ))}
                </Stack>
              </div>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="docs" pt="md">
          <Stack gap="md">
            <Group justify="space-between" align="center">
              <div>
                <Title order={4}>Documentation Status</Title>
                <Text size="sm" c="dimmed" mt="xs">
                  Device documentation ingestion status
                </Text>
              </div>
              <Badge
                color={
                  device.docs_status === 'success'
                    ? 'green'
                    : device.docs_status === 'partial'
                    ? 'blue'
                    : device.docs_status === 'error'
                    ? 'red'
                    : 'gray'
                }
                size="lg"
              >
                {device.docs_status || 'pending'}
              </Badge>
            </Group>

            {device.docs_ingested && device.docs_ingested_at && (
              <Paper p="md" withBorder bg="green.0">
                <Group gap="xs">
                  <FileText size={20} color="#40c057" />
                  <div>
                    <Text size="sm" fw={500}>
                      Documentation Successfully Ingested
                    </Text>
                    <Text size="xs" c="dimmed">
                      Ingested at{' '}
                      {new Date(device.docs_ingested_at).toLocaleString()}
                    </Text>
                  </div>
                </Group>
              </Paper>
            )}

            {!device.docs_ingested && (
              <Paper p="md" withBorder bg="gray.0">
                <Text size="sm" c="dimmed">
                  Device documentation is awaiting ingestion. The system will
                  automatically discover and process documentation for this device,
                  including manuals, forum discussions, and technical specifications.
                </Text>
              </Paper>
            )}

            <div>
              <Title order={5} mb="xs">
                About This Device
              </Title>
              <Text size="sm" c="dimmed">
                {device.name} is a {device.type} device integrated via{' '}
                {device.integration}.
                {device.metadata?.manufacturer && (
                  <> Manufactured by {device.metadata.manufacturer}</>
                )}
                {device.metadata?.model && (
                  <>, Model: {device.metadata.model}</>
                )}.
              </Text>
            </div>

            {knowledgeBase && knowledgeBase.articles.length > 0 && (
              <div>
                <Title order={5} mb="md">
                  Knowledge Base Articles
                </Title>
                <Stack gap="md">
                  {knowledgeBase.articles.map((article, idx) => (
                    <Paper key={idx} p="md" withBorder bg={article.available ? 'blue.0' : 'gray.0'}>
                      <Group justify="space-between" align="flex-start" mb="xs">
                        <div style={{ flex: 1 }}>
                          <Text size="sm" fw={600}>{article.title}</Text>
                          <Text size="xs" c="dimmed" mt="xs">
                            {article.source}
                          </Text>
                        </div>
                        <Badge size="sm" variant={article.available ? 'light' : 'outline'} color={article.available ? 'green' : 'gray'}>
                          {article.available ? 'Available' : 'Pending'}
                        </Badge>
                      </Group>
                      <div style={{ fontSize: '0.875rem', lineHeight: 1.5 }}>
                        <ReactMarkdown>{article.description}</ReactMarkdown>
                      </div>
                    </Paper>
                  ))}
                </Stack>
                <Text size="sm" c="dimmed" mt="md">
                  You can use the AI chat feature to ask questions about this device based on these knowledge base articles.
                </Text>
              </div>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
