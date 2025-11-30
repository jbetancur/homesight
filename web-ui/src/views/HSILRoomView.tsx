import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Container,
  Grid,
  Card,
  Text,
  Badge,
  Group,
  Stack,
  Textarea,
  Button,
  Paper,
  Box,
  ThemeIcon,
  rem,
  Modal,
  Select,
} from '@mantine/core';
import {
  Thermometer,
  Droplet,
  Flame,
  Zap,
  AlertTriangle,
  Send,
  Brain,
  Sparkles,
  Cloud,
  Wind,
  Sunrise,
  Sunset,
} from 'lucide-react';
import { API_BASE } from '../apiConfig';
import { useEventSubscription } from '../useEventSubscription';

interface Device {
  id: string;
  name: string;
  type: string;
  value: number | boolean | null;
  state: 'normal' | 'warning' | 'critical' | 'unknown';
  location: string;
  zone_id?: string;
  unit?: string;
  active: boolean;
  last_updated: string;
  trend?: 'up' | 'down' | 'stable';
}

interface Room {
  id: string;
  name: string;
  devices: Device[];
}

interface AIMessage {
  role: 'user' | 'assistant';
  content: string;
  action?: any;
}

const ZONE_ICONS: Record<string, any> = {
  'living-room': Thermometer,
  kitchen: Flame,
  bedroom: Thermometer,
  bathroom: Droplet,
  basement: Droplet,
  garage: Zap,
};

const DEVICE_ICONS: Record<string, any> = {
  temp: Thermometer,
  temperature: Thermometer,
  humidity: Droplet,
  leak: Droplet,
  motion: Zap,
  water_leak: Droplet,
};

const getStateColor = (state: string) => {
  switch (state) {
    case 'critical':
      return 'red';
    case 'warning':
      return 'yellow';
    case 'normal':
      return 'green';
    default:
      return 'gray';
  }
};

export default function HSILRoomView() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [availableZones, setAvailableZones] = useState<any[]>([]);
  const [chatMessages, setChatMessages] = useState<AIMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [aiThinking, setAiThinking] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedZone, setSelectedZone] = useState<string>('');
  const [weather, setWeather] = useState<any>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Helper to check if device was recently updated (within last 30 seconds)
  const isRecentlyUpdated = (lastUpdated: string | undefined) => {
    if (!lastUpdated) return false;
    const updateTime = new Date(lastUpdated).getTime();
    const now = new Date().getTime();
    const thirtySecondsAgo = now - 30000;
    return updateTime > thirtySecondsAgo;
  };

  useEffect(() => {
    fetchRoomsAndDevices();
    fetchWeather();
    const weatherInterval = setInterval(fetchWeather, 900000); // 15 minutes
    return () => {
      clearInterval(weatherInterval);
    };
  }, []);

  useEffect(() => {
    // Auto-scroll to latest message
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Real-time event handling
  const handleEvent = useCallback((event: any) => {
    // Refresh devices on incident added/removed/updated
    if (event.type === "incident_added" ||
        event.type === "incident_removed" ||
        event.type === "incident_updated") {
      fetchRoomsAndDevices();
    }
  }, []);

  useEventSubscription(handleEvent);

  const fetchWeather = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/hsil/weather`);
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
        setAvailableZones(zones);
      }

      // Group devices by room/zone
      const roomMap = new Map<string, Room>();

      // Add all available zones as rooms
      zones.forEach((zone: any) => {
        roomMap.set(zone.id, {
          id: zone.id,
          name: zone.name,
          devices: [],
        });
      });

      // Add devices to their respective rooms
      devices.forEach((device: any) => {
        const zoneId = device.zone_id || 'unassigned';
        if (!roomMap.has(zoneId)) {
          roomMap.set(zoneId, {
            id: zoneId,
            name: zoneId === 'unassigned' ? 'Unassigned Devices' : zoneId,
            devices: [],
          });
        }
        roomMap.get(zoneId)!.devices.push({
          id: device.id,
          name: device.name,
          type: device.type,
          value: device.value,
          state: device.state || 'unknown',
          location: device.zone_id || 'unassigned',
          zone_id: device.zone_id,
          unit: device.unit,
          active: device.active || false,
          last_updated: device.last_seen || device.last_updated,
          trend: device.trend,
        });
      });

      setRooms(Array.from(roomMap.values()));
    } catch (error) {
      console.error('Failed to fetch rooms:', error);
    }
  };

  const handleChatSubmit = async () => {
    if (!chatInput.trim()) return;

    const userMessage: AIMessage = { role: 'user', content: chatInput };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput('');
    setChatLoading(true);
    setAiThinking(true);

    try {
      const res = await fetch(`${API_BASE}/api/hsil/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: chatInput }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMessage: AIMessage = {
          role: 'assistant',
          content: data.reply,
          action: data.action,
        };
        setChatMessages((prev) => [...prev, assistantMessage]);

        if (data.action) {
          // Flash the affected device/room
          setAiThinking(false);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
    } finally {
      setChatLoading(false);
      setAiThinking(false);
    }
  };

  const handleDeviceZoneUpdate = async (deviceId: string, zoneId: string) => {
    try {
      await fetch(`${API_BASE}/api/devices/${deviceId}/zone`, {
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
                  HomeSight Intelligence Layer
                </Text>
                <Text size="sm" c="rgba(255,255,255,0.8)">
                  AI-Powered Home Automation & Learning System
                </Text>
              </div>
            </Group>
            {aiThinking && (
              <Group>
                <Sparkles size={20} color="white" />
                <Text size="sm" c="white" fw={500}>
                  AI Processing...
                </Text>
              </Group>
            )}
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
                  <Text size="xs" c="dimmed">Feels like {Math.round(weather.weather?.feels_like || 0)}°F</Text>
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

        {/* Room Grid */}
        <Grid>
          {rooms.map((room) => {
            const hasCritical = room.devices.some(d => d.state === 'critical' || d.active);
            const hasWarning = room.devices.some(d => d.state === 'warning');

            return (
              <Grid.Col key={room.id} span={{ base: 12, sm: 6, md: 4 }}>
                <Card
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
                    borderWidth: hasCritical ? '2px' : '1px',
                    transition: 'all 0.3s ease-in-out',
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
                      <Badge
                        size="sm"
                        variant="light"
                        color={hasCritical ? 'red' : hasWarning ? 'yellow' : undefined}
                      >
                        {room.devices.length} {room.devices.length === 1 ? 'device' : 'devices'}
                      </Badge>
                    </Group>
                  </Card.Section>

                <Stack gap="xs" mt="md">
                  {room.devices.length === 0 ? (
                    <Text size="sm" c="dimmed" ta="center" py="md">
                      No devices assigned
                    </Text>
                  ) : (
                    room.devices.map((device) => {
                      const Icon = DEVICE_ICONS[device.type] || Zap;
                      const recentlyUpdated = isRecentlyUpdated(device.last_updated);

                      return (
                        <Paper
                          key={device.id}
                          p="sm"
                          radius="md"
                          withBorder
                          style={{
                            cursor: 'pointer',
                            transition: 'all 0.3s ease-in-out',
                            borderWidth: device.active || device.state === 'critical' ? '2px' : '1px',
                            borderColor:
                              device.active || device.state === 'critical'
                                ? 'var(--mantine-color-red-6)'
                                : device.state === 'warning'
                                  ? 'var(--mantine-color-yellow-6)'
                                  : recentlyUpdated
                                    ? 'var(--mantine-color-blue-5)'
                                    : undefined,
                            backgroundColor:
                              device.active || device.state === 'critical'
                                ? 'var(--mantine-color-red-0)'
                                : device.state === 'warning'
                                  ? 'var(--mantine-color-yellow-0)'
                                  : recentlyUpdated
                                    ? 'var(--mantine-color-blue-0)'
                                    : undefined,
                            boxShadow:
                              device.active || device.state === 'critical'
                                ? '0 0 20px rgba(250, 82, 82, 0.5)'
                                : device.state === 'warning'
                                  ? '0 0 15px rgba(250, 176, 5, 0.3)'
                                  : undefined,
                          }}
                          onClick={() => {
                            setSelectedDevice(device);
                            setSelectedZone(device.zone_id || '');
                            setShowSettings(true);
                          }}
                        >
                          <Group justify="space-between">
                            <Group gap="xs">
                              <ThemeIcon
                                size="sm"
                                variant="light"
                                color={getStateColor(device.state)}
                              >
                                <Icon size={14} />
                              </ThemeIcon>
                              <Text size="sm" fw={500}>
                                {device.name}
                              </Text>
                            </Group>
                            <Group gap="xs">
                              {device.value !== null && device.value !== undefined && (
                                <Text size="sm" fw={600}>
                                  {typeof device.value === 'boolean'
                                    ? device.value
                                      ? 'Active'
                                      : 'Inactive'
                                    : `${device.value}${device.unit || ''}`}
                                </Text>
                              )}
                              {device.active && (
                                <ThemeIcon size="xs" color="red" variant="filled">
                                  <AlertTriangle size={10} />
                                </ThemeIcon>
                              )}
                            </Group>
                          </Group>
                        </Paper>
                      );
                    })
                  )}
                </Stack>
              </Card>
            </Grid.Col>
            );
          })}
        </Grid>

        {/* AI Chat Panel */}
        <Paper shadow="md" p="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group>
              <ThemeIcon size="lg" variant="gradient" gradient={{ from: 'indigo', to: 'cyan' }}>
                <Brain size={20} />
              </ThemeIcon>
              <Text size="lg" fw={600}>
                AI Assistant
              </Text>
            </Group>

            <Box
              style={{
                maxHeight: rem(300),
                overflowY: 'auto',
                padding: rem(12),
                backgroundColor: 'var(--mantine-color-gray-0)',
                borderRadius: rem(8),
              }}
            >
              {chatMessages.length === 0 ? (
                <Text size="sm" c="dimmed" ta="center" py="md">
                  Ask me anything about your home, or tell me how you'd like to adjust things!
                </Text>
              ) : (
                <Stack gap="md">
                  {chatMessages.map((msg, idx) => (
                    <Paper
                      key={idx}
                      p="sm"
                      radius="md"
                      style={{
                        backgroundColor:
                          msg.role === 'user'
                            ? 'var(--mantine-color-blue-6)'
                            : 'var(--mantine-color-gray-2)',
                        color: msg.role === 'user' ? 'white' : 'inherit',
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                      }}
                    >
                      <Text size="sm">{msg.content}</Text>
                      {msg.action && (
                        <Badge size="xs" mt="xs" color="green">
                          Action: {msg.action.command}
                        </Badge>
                      )}
                    </Paper>
                  ))}
                  <div ref={chatEndRef} />
                </Stack>
              )}
            </Box>

            <Group gap="xs" align="flex-end">
              <Textarea
                placeholder="Type your message..."
                value={chatInput}
                onChange={(e) => setChatInput(e.currentTarget.value)}
                onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleChatSubmit()}
                autosize
                minRows={1}
                maxRows={4}
                style={{ flex: 1 }}
              />
              <Button
                onClick={handleChatSubmit}
                loading={chatLoading}
                leftSection={<Send size={16} />}
              >
                Send
              </Button>
            </Group>
          </Stack>
        </Paper>
      </Stack>

      {/* Device Settings Modal */}
      <Modal
        opened={showSettings && selectedDevice !== null}
        onClose={() => {
          setShowSettings(false);
          setSelectedDevice(null);
          setSelectedZone('');
        }}
        title={`Configure: ${selectedDevice?.name}`}
      >
        <Stack gap="md">
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
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (selectedZone && selectedDevice) {
                  handleDeviceZoneUpdate(selectedDevice.id, selectedZone);
                }
              }}
              disabled={!selectedZone}
            >
              Save
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  );
}
