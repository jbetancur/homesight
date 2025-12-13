import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Stack, Title, Text, Card, Group, Badge, Loader, Button, Paper, Tabs,
  Grid, ActionIcon, Tooltip, Progress, Modal, TextInput
} from '@mantine/core';
import {
  ArrowLeft, FileText, Activity, Droplets, Thermometer, Info, Clock, RefreshCw,
  AlertCircle, CheckCircle, Battery, Zap, Power, Eye, Edit2
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEventSubscription } from '../useEventSubscription';
import { API_BASE_WITH_PATHS } from '../apiConfig';
import { CapabilityWidget } from '../components/DeviceCapabilityWidgets';
import { EntityGrid } from '../components/EntityGrid';
import { SensorTimeSeriesChart } from '../components/SensorTimeSeriesChart';

const API_BASE = API_BASE_WITH_PATHS;

interface DeviceReadings {
  temperature_f?: number;
  humidity?: number;
  water?: boolean;
  motion?: boolean;
  contact?: boolean;
  tamper?: boolean;
  smoke?: boolean;
  co?: boolean;
  power_w?: number;
  energy_kwh?: number;
  voltage_v?: number;
  current_a?: number;
  illuminance?: number;
  co2?: number;
  voc?: number;
  pm25?: number;
  pressure?: number;
  uv_index?: number;
}

interface DeviceBattery {
  level: number;
  is_low: boolean;
  is_charging: boolean;
}

interface DeviceConnectivity {
  online: boolean;
  signal_strength?: number;
  last_seen: string;
  firmware_version?: string;
}

interface DeviceControls {
  switch?: { value: boolean; settable: boolean };
  level?: { value: number; settable: boolean; min: number; max: number };
  color?: { r: number; g: number; b: number; settable: boolean };
  thermostat?: { mode: string; setpoint_heat?: number; setpoint_cool?: number; settable: boolean };
  lock?: { locked: boolean; settable: boolean };
}

interface DeviceEntity {
  id: string;
  device_id: string;
  entity_type: 'sensor' | 'binary_sensor' | 'switch' | 'number' | 'alarm' | 'diagnostic' | 'config';
  name: string;
  category: string;
  value: any;
  unit: string;
  settable: boolean;
  metadata: Record<string, any>;
  updated_at: string;
}

interface Device {
  id: string;
  name: string;
  display_name?: string;
  type: string;
  integration: string;
  manufacturer?: string;
  model?: string;
  capabilities?: string[];

  // Unified contract
  readings?: DeviceReadings;
  controls?: DeviceControls;
  battery?: DeviceBattery;
  connectivity?: DeviceConnectivity;
  raw_data?: Record<string, any>;

  // Entity-Based Model (New - more flexible)
  entities?: DeviceEntity[];

  // Backward compatibility (API still includes these)
  state?: Record<string, any>;
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
  docs_status: string;
  docs_ingested: boolean;
  ingested_at?: string;
  content?: string;
  source?: string;
  manufacturer?: string;
  model?: string;
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
    'air_temperature': 'air_temperature', // Keep air_temperature separate to detect Fahrenheit
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
    case 'temperature_f': {
      // Use standardized Fahrenheit temperature (backend converts all temps to F)
      const tempValue = typeof value === 'number' ? value : parseFloat(String(value));
      if (isNaN(tempValue)) return null;

      return {
        icon: <Thermometer size={20} color="#228be6" />,
        display: `${tempValue.toFixed(1)}°F`,
        label: 'Temperature'
      };
    }
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
      // Skip object values (e.g., complex Z-Wave values)
      if (typeof value === 'object') return null;

      return {
        icon: <Activity size={20} color="#868e96" />,
        display: String(value),
        label: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      };
  }
}

export function DeviceOverviewView() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<Device | null>(null);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [aliasModalOpen, setAliasModalOpen] = useState(false);
  const [editingAlias, setEditingAlias] = useState('');
  const [savingAlias, setSavingAlias] = useState(false);
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

  const capabilities = device.capabilities || [];

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

  const openAliasModal = () => {
    setEditingAlias(device?.display_name || '');
    setAliasModalOpen(true);
  };

  const handleSaveAlias = async () => {
    if (!deviceId) return;
    
    setSavingAlias(true);
    try {
      const response = await fetch(`${API_BASE}/devices/${deviceId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: editingAlias.trim() }),
      });
      
      if (response.ok) {
        const updatedDevice = await response.json();
        setDevice(updatedDevice);
        deviceRef.current = updatedDevice;
        setAliasModalOpen(false);
      } else {
        console.error('Failed to save display name');
      }
    } catch (error) {
      console.error('Error saving display name:', error);
    } finally {
      setSavingAlias(false);
    }
  };

  // Get the display name (display_name if set, otherwise original name)
  const displayName = device?.display_name || device?.name || 'Unknown Device';

  return (
    <Stack gap="md">
      {/* Alias Edit Modal */}
      <Modal
        opened={aliasModalOpen}
        onClose={() => setAliasModalOpen(false)}
        title="Edit Device Name"
        size="sm"
      >
        <Stack gap="md">
          <TextInput
            label="Friendly Name"
            description="Give this device a custom name (leave empty to use original name)"
            placeholder={device?.name || 'Enter a friendly name'}
            value={editingAlias}
            onChange={(e) => setEditingAlias(e.target.value)}
          />
          <Text size="xs" c="dimmed">
            Original name: {device?.name}
          </Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="subtle" onClick={() => setAliasModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveAlias} loading={savingAlias}>
              Save
            </Button>
          </Group>
        </Stack>
      </Modal>

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
                <Title order={2}>{displayName}</Title>
                <Tooltip label="Edit device name">
                  <ActionIcon variant="subtle" size="sm" onClick={openAliasModal}>
                    <Edit2 size={16} />
                  </ActionIcon>
                </Tooltip>
              </Group>
              <Group gap="sm">
                <Badge variant="light" color="blue">{device.type}</Badge>
                <Badge variant="outline">{device.integration}</Badge>
                {device.display_name && (
                  <Text size="xs" c="dimmed">Original: {device.name}</Text>
                )}
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
                    <Text size="sm" fw={500}>{device.manufacturer || '-'}</Text>
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
                    <Text size="sm" fw={500}>{device.model || '-'}</Text>
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
      {((device.readings && Object.keys(device.readings).length > 0) ||device.battery?.level !== undefined || device.battery) && (
        <Card withBorder p="lg">
          <Stack gap="md">
            <Text fw={600} size="lg">Current Readings</Text>
            <Grid>
              {/* Battery Status - check both unified contract and legacy field */}
              {device.battery && (() => {
                const batteryLevel = device.battery?.level;
                const batteryLow = device.battery?.is_low; 

                if (batteryLevel === undefined) return null;

                return (
                  <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
                    <Paper p="md" withBorder bg={batteryLow ? 'red.0' : 'green.0'} radius="md">
                      <Group justify="space-between">
                        <Group gap="sm">
                          <Battery size={24} color={batteryLow ? '#fa5252' : '#40c057'} />
                          <div>
                            <Text size="xs" c="dimmed">Battery</Text>
                            <Text fw={600} size="lg" c={getBatteryColor(batteryLevel)}>
                              {batteryLevel}%
                            </Text>
                            {device.battery?.is_charging && (
                              <Text size="xs" c="green">Charging</Text>
                            )}
                          </div>
                        </Group>
                        <Progress
                          value={batteryLevel}
                          size="xl"
                          w={60}
                          color={getBatteryColor(batteryLevel)}
                        />
                      </Group>
                    </Paper>
                  </Grid.Col>
                );
              })()}
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
      <Tabs defaultValue={device.entities && device.entities.length > 0 ? "entities" : "controls"}>
        <Tabs.List>
          {device.entities && device.entities.length > 0 && (
            <Tabs.Tab value="entities">
              All Entities
              <Badge size="sm" color="blue" ml={5}>
                {device.entities.length}
              </Badge>
            </Tabs.Tab>
          )}
          <Tabs.Tab value="controls">Controls</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
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

        {/* Entities Tab - New entity-based model */}
        {device.entities && device.entities.length > 0 && (
          <Tabs.Panel value="entities" pt="md">
            <Card withBorder p="lg">
              <EntityGrid entities={device.entities} onUpdate={handleRefresh} />
            </Card>
          </Tabs.Panel>
        )}

        {/* Controls Tab - Unified contract controls */}
        <Tabs.Panel value="controls" pt="md">
          {(!device.controls || Object.keys(device.controls).length === 0) ? (
            <Card withBorder p="xl">
              <Stack align="center" gap="md">
                <Activity size={48} color="#868e96" />
                <div style={{ textAlign: 'center' }}>
                  <Text size="lg" fw={600}>No Controls Available</Text>
                  <Text size="sm" c="dimmed">
                    This device doesn't have any controllable features
                  </Text>
                </div>
              </Stack>
            </Card>
          ) : (
            <Grid>
              {/* Switch Control */}
              {device.controls.switch && (
                <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
                  <Card withBorder p="md">
                    <Stack gap="sm">
                      <Group justify="space-between">
                        <Text fw={600}>Switch</Text>
                        <Badge color={device.controls.switch.value ? 'green' : 'gray'}>
                          {device.controls.switch.value ? 'ON' : 'OFF'}
                        </Badge>
                      </Group>
                      {device.controls.switch.settable && (
                        <Button
                          fullWidth
                          variant={device.controls.switch.value ? 'light' : 'filled'}
                          color={device.controls.switch.value ? 'red' : 'green'}
                          onClick={async () => {
                            if (!device.controls?.switch) return;
                            const newValue = !device.controls.switch.value;
                            try {
                              const response = await fetch(`${API_BASE}/devices/${device.id}/command`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  command: 'set_switch',
                                  args: { on: newValue }
                                })
                              });
                              if (!response.ok) throw new Error('Failed to send command');
                              console.log('Switch command sent successfully');
                              // Refresh device state after a delay to allow Z-Wave to update
                              setTimeout(async () => {
                                const deviceRes = await fetch(`${API_BASE}/devices/${device.id}`);
                                if (deviceRes.ok) {
                                  const deviceData = await deviceRes.json();
                                  setDevice(deviceData);
                                }
                              }, 1000);
                            } catch (error) {
                              console.error('Failed to toggle switch:', error);
                            }
                          }}
                        >
                          Turn {device.controls.switch.value ? 'Off' : 'On'}
                        </Button>
                      )}
                    </Stack>
                  </Card>
                </Grid.Col>
              )}

              {/* Level Control */}
              {device.controls.level && (
                <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
                  <Card withBorder p="md">
                    <Stack gap="sm">
                      <Text fw={600}>Level</Text>
                      <Progress value={device.controls.level.value} size="lg" />
                      <Text size="sm" c="dimmed">
                        {device.controls.level.value}% ({device.controls.level.min}-{device.controls.level.max})
                      </Text>
                    </Stack>
                  </Card>
                </Grid.Col>
              )}

              {/* Capability widgets for backward compatibility */}
              {device.capabilities && device.capabilities.map((capability: string, idx: number) => (
                <Grid.Col key={idx} span={{ base: 12, sm: 6, md: 4 }}>
                  <CapabilityWidget
                    deviceId={device.id}
                    capability={capability}
                    state={device.readings || {}}
                    metadata={device.raw_data}
                  />
                </Grid.Col>
              ))}
            </Grid>
          )}
        </Tabs.Panel>

        {/* History Tab - Time-series sensor data */}
        <Tabs.Panel value="history" pt="md">
          <SensorTimeSeriesChart deviceId={device.id} />
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
                <Text fw={500}>{device.manufacturer || '-'}</Text>
              </div>
              <div style={{ flex: 1 }}>
                <Text size="sm" c="dimmed">Model</Text>
                <Text fw={500}>{device.model || '-'}</Text>
              </div>
            </Group>
            {Object.keys(device.raw_data || {}).length > 0 && (
              <div>
                <Text size="sm" c="dimmed" mb="xs">
                  Raw Integration Data
                </Text>
                <Stack gap="xs">
                  {Object.entries(device.raw_data || {})
                    .filter(([key]) => !key.startsWith('_'))
                    .map(([key, value]) => {
                      // Format value based on type
                      let displayValue: string;
                      if (value === null || value === undefined) {
                        displayValue = '-';
                      } else if (typeof value === 'object') {
                        // For objects/arrays, show JSON or count
                        if (Array.isArray(value)) {
                          displayValue = `[${value.length} items]`;
                        } else {
                          displayValue = `{${Object.keys(value).length} properties}`;
                        }
                      } else {
                        displayValue = String(value);
                      }

                      return (
                        <Group key={key} justify="space-between">
                          <Text size="sm" c="dimmed">
                            {key.replace(/_/g, ' ')}
                          </Text>
                          <Text size="sm">{displayValue}</Text>
                        </Group>
                      );
                    })}
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
                {device.manufacturer && (
                  <> Manufactured by {device.manufacturer}</>
                )}
                {device.model && (
                  <>, Model: {device.model}</>
                )}.
              </Text>
            </div>

            {knowledgeBase && knowledgeBase.content && (
              <div>
                <Group justify="space-between" align="center" mb="md">
                  <Title order={5}>Knowledge Base</Title>
                  {knowledgeBase.source && (
                    <Text size="xs" c="dimmed">{knowledgeBase.source}</Text>
                  )}
                </Group>
                <Paper p="md" withBorder>
                  <div style={{ fontSize: '0.875rem', lineHeight: 1.6 }} className="markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {knowledgeBase.content
                        .replace(/^```(?:markdown)?\s*\n?/i, '')
                        .replace(/\n?```\s*$/i, '')}
                    </ReactMarkdown>
                  </div>
                </Paper>
                <Text size="sm" c="dimmed" mt="md">
                  You can use the AI chat feature to ask questions about this device based on this knowledge base.
                </Text>
              </div>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
