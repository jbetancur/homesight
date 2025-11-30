/**
 * HSIL (HomeSight Intelligence Layer) Dashboard View
 *
 * Displays:
 * - Device tiles with current state
 * - Learned preferences
 * - System learning statistics
 * - Chat interface
 */

import { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Card,
  Text,
  Badge,
  Group,
  Stack,
  Title,
  ActionIcon,
  Loader,
  Box,
  Paper,
  Drawer,
  TextInput,
  Button,
  RingProgress,
  ThemeIcon,
} from '@mantine/core';
import {
  Thermometer,
  Droplets,
  AlertTriangle,
  Activity,
  MessageCircle,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;


interface DeviceState {
  id: string;
  type: string;
  label: string;
  state: 'normal' | 'warning' | 'critical' | 'unknown';
  value: number | string | boolean | null;
  active: boolean;
  location: string;
  unit?: string;
  last_updated: string;
  trend?: string;
}

interface HomeState {
  devices: DeviceState[];
  timestamp: string;
  summary?: Record<string, unknown>;
}

interface HSILStats {
  hsil_version: string;
  adaptive_learning: {
    user_preference_events: number;
    device_baselines_learned: number;
    comfort_preferences_learned: number;
    action_outcomes_recorded: number;
    recent_success_rate: number;
    locations_with_preferences: number;
  };
  feedback_learning: {
    total_interactions: number;
    feedback_counts: Record<string, number>;
    high_confidence_preferences: number;
    learning_rate: number;
  };
  timestamp: string;
}

export function HSILView() {
  const [homeState, setHomeState] = useState<HomeState | null>(null);
  const [stats, setStats] = useState<HSILStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<DeviceState | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<Array<{ role: string; content: string }>>([]);

  // Fetch home state
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [stateRes, statsRes] = await Promise.all([
          fetch(`${API_BASE}/hsil/state`),
          fetch(`${API_BASE}/hsil/stats`),
        ]);

        if (stateRes.ok) {
          const data = await stateRes.json();
          setHomeState(data);
        }

        if (statsRes.ok) {
          const data = await statsRes.json();
          setStats(data);
        }
      } catch (error) {
        console.error('Failed to fetch HSIL data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000); // Update every 5 seconds

    return () => clearInterval(interval);
  }, []);

  // Send chat message
  const handleSendMessage = async () => {
    if (!chatMessage.trim()) return;

    const userMessage = chatMessage;
    setChatMessage('');
    setChatHistory((prev) => [...prev, { role: 'user', content: userMessage }]);

    try {
      const res = await fetch(`${API_BASE}/hsil/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      });

      if (res.ok) {
        const data = await res.json();
        setChatHistory((prev) => [...prev, { role: 'assistant', content: data.reply }]);

        if (data.action) {
          setChatHistory((prev) => [
            ...prev,
            {
              role: 'system',
              content: `Action: ${data.action.command} (${data.action.topic})`,
            },
          ]);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
    }
  };

  // Get icon for device type
  const getDeviceIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'temp':
      case 'temperature':
        return <Thermometer size={24} />;
      case 'humidity':
        return <Droplets size={24} />;
      case 'leak':
      case 'water':
        return <AlertTriangle size={24} />;
      default:
        return <Activity size={24} />;
    }
  };

  // Get color for device state
  const getStateColor = (state: string): string => {
    switch (state) {
      case 'normal':
        return 'green';
      case 'warning':
        return 'yellow';
      case 'critical':
        return 'red';
      default:
        return 'gray';
    }
  };

  // Get trend icon
  const getTrendIcon = (trend?: string) => {
    if (trend === 'up') return <TrendingUp size={16} color="red" />;
    if (trend === 'down') return <TrendingDown size={16} color="blue" />;
    return <Minus size={16} color="gray" />;
  };

  if (loading) {
    return (
      <Container size="xl" py="xl">
        <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
          <Loader size="xl" />
          <Text>Loading HSIL...</Text>
        </Stack>
      </Container>
    );
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between">
          <div>
            <Title order={1}>HomeSight Intelligence Layer</Title>
            <Text size="sm" c="dimmed">
              Adaptive learning &middot; Predictive intelligence &middot; Natural language control
            </Text>
          </div>
          <ActionIcon
            variant="filled"
            size="xl"
            radius="xl"
            onClick={() => setChatOpen(true)}
          >
            <MessageCircle size={24} />
          </ActionIcon>
        </Group>

        {/* Learning Stats */}
        {stats && (
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Paper p="md" radius="md" withBorder>
                <Group justify="space-between">
                  <div>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Baselines Learned
                    </Text>
                    <Text size="xl" fw={700}>
                      {stats.adaptive_learning.device_baselines_learned}
                    </Text>
                  </div>
                  <RingProgress
                    size={60}
                    thickness={6}
                    sections={[
                      {
                        value:
                          (stats.adaptive_learning.device_baselines_learned / 50) * 100,
                        color: 'blue',
                      },
                    ]}
                  />
                </Group>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Paper p="md" radius="md" withBorder>
                <div>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    User Interactions
                  </Text>
                  <Text size="xl" fw={700}>
                    {stats.feedback_learning.total_interactions}
                  </Text>
                  <Text size="xs" c="dimmed" mt="xs">
                    Learning rate: {(stats.feedback_learning.learning_rate * 100).toFixed(1)}%
                  </Text>
                </div>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Paper p="md" radius="md" withBorder>
                <div>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Comfort Preferences
                  </Text>
                  <Text size="xl" fw={700}>
                    {stats.adaptive_learning.comfort_preferences_learned}
                  </Text>
                  <Text size="xs" c="dimmed" mt="xs">
                    {stats.adaptive_learning.locations_with_preferences} locations
                  </Text>
                </div>
              </Paper>
            </Grid.Col>

            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Paper p="md" radius="md" withBorder>
                <div>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Success Rate
                  </Text>
                  <Text size="xl" fw={700}>
                    {(stats.adaptive_learning.recent_success_rate * 100).toFixed(0)}%
                  </Text>
                  <Text size="xs" c="dimmed" mt="xs">
                    Last 7 days
                  </Text>
                </div>
              </Paper>
            </Grid.Col>
          </Grid>
        )}

        {/* Device Tiles */}
        <div>
          <Title order={2} mb="md">
            Device Dashboard
          </Title>
          <Grid>
            {homeState?.devices.map((device) => (
              <Grid.Col key={device.id} span={{ base: 12, sm: 6, md: 4, lg: 3 }}>
                <Card
                  shadow="sm"
                  padding="lg"
                  radius="md"
                  withBorder
                  style={{
                    cursor: 'pointer',
                    borderColor:
                      device.state === 'critical'
                        ? 'var(--mantine-color-red-6)'
                        : device.state === 'warning'
                        ? 'var(--mantine-color-yellow-6)'
                        : undefined,
                  }}
                  onClick={() => setSelectedDevice(device)}
                >
                  <Stack gap="xs">
                    <Group justify="space-between">
                      <ThemeIcon
                        size="xl"
                        radius="md"
                        variant="light"
                        color={getStateColor(device.state)}
                      >
                        {getDeviceIcon(device.type)}
                      </ThemeIcon>
                      <Badge color={getStateColor(device.state)} variant="light">
                        {device.state}
                      </Badge>
                    </Group>

                    <div>
                      <Text fw={500} size="sm">
                        {device.label}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {device.location}
                      </Text>
                    </div>

                    <Group justify="space-between" align="baseline">
                      <Text size="xl" fw={700}>
                        {typeof device.value === 'number'
                          ? device.value.toFixed(1)
                          : device.value}
                        {device.unit && (
                          <Text component="span" size="sm" c="dimmed" ml={4}>
                            {device.unit}
                          </Text>
                        )}
                      </Text>
                      {getTrendIcon(device.trend)}
                    </Group>

                    {device.active && (
                      <Badge color="blue" variant="filled" fullWidth>
                        Active
                      </Badge>
                    )}
                  </Stack>
                </Card>
              </Grid.Col>
            ))}
          </Grid>
        </div>
      </Stack>

      {/* Device Detail Drawer */}
      <Drawer
        opened={selectedDevice !== null}
        onClose={() => setSelectedDevice(null)}
        title={selectedDevice?.label}
        position="right"
        size="md"
      >
        {selectedDevice && (
          <Stack gap="md">
            <Group>
              <Badge color={getStateColor(selectedDevice.state)} variant="light" size="lg">
                {selectedDevice.state.toUpperCase()}
              </Badge>
              {selectedDevice.active && (
                <Badge color="blue" variant="filled" size="lg">
                  ACTIVE
                </Badge>
              )}
            </Group>

            <div>
              <Text size="sm" c="dimmed">
                Location
              </Text>
              <Text size="lg">{selectedDevice.location}</Text>
            </div>

            <div>
              <Text size="sm" c="dimmed">
                Current Value
              </Text>
              <Text size="xl" fw={700}>
                {typeof selectedDevice.value === 'number'
                  ? selectedDevice.value.toFixed(1)
                  : selectedDevice.value}
                {selectedDevice.unit && ` ${selectedDevice.unit}`}
              </Text>
            </div>

            <div>
              <Text size="sm" c="dimmed">
                Last Updated
              </Text>
              <Text size="sm">{new Date(selectedDevice.last_updated).toLocaleString()}</Text>
            </div>

            {selectedDevice.trend && (
              <div>
                <Text size="sm" c="dimmed">
                  Trend
                </Text>
                <Group gap="xs">
                  {getTrendIcon(selectedDevice.trend)}
                  <Text size="sm">{selectedDevice.trend}</Text>
                </Group>
              </div>
            )}
          </Stack>
        )}
      </Drawer>

      {/* Chat Drawer */}
      <Drawer
        opened={chatOpen}
        onClose={() => setChatOpen(false)}
        title="Chat with HSIL"
        position="right"
        size="lg"
      >
        <Stack gap="md" style={{ height: '100%' }}>
          <Box style={{ flex: 1, overflow: 'auto' }}>
            <Stack gap="sm">
              {chatHistory.map((msg, idx) => (
                <Paper
                  key={idx}
                  p="sm"
                  radius="md"
                  bg={msg.role === 'user' ? 'blue.0' : msg.role === 'system' ? 'gray.1' : 'white'}
                  withBorder={msg.role !== 'user'}
                >
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {msg.role}
                  </Text>
                  <Text size="sm">{msg.content}</Text>
                </Paper>
              ))}
            </Stack>
          </Box>

          <Group>
            <TextInput
              style={{ flex: 1 }}
              placeholder="Ask about your home..."
              value={chatMessage}
              onChange={(e) => setChatMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendMessage();
              }}
            />
            <Button onClick={handleSendMessage}>Send</Button>
          </Group>
        </Stack>
      </Drawer>
    </Container>
  );
}
