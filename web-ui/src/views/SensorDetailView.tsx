import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Stack, Title, Text, Card, Group, Badge, Loader, Button, Grid, Paper, Tabs } from '@mantine/core';
import { ArrowLeft, Activity, TrendingUp, Calendar } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_BASE_WITH_PATHS } from '../apiConfig';

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
  metadata: Record<string, string>;
  docs_ingested: boolean;
  docs_ingested_at: string;
  docs_status: string;
}

interface MetricPoint {
  timestamp: string;
  value: number;
  labels?: Record<string, string>;
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

export function SensorDetailView() {
  const { deviceId, sensorId } = useParams<{ deviceId: string; sensorId: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<Device | null>(null);
  const [sensor, setSensor] = useState<Sensor | null>(null);
  const [metrics, setMetrics] = useState<MetricPoint[]>([]);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        // Fetch device
        if (deviceId) {
          const deviceRes = await fetch(`${API_BASE}/devices/${deviceId}`);
          if (!deviceRes.ok) throw new Error('Failed to fetch device');
          const deviceData = await deviceRes.json();
          setDevice(deviceData);

          // Fetch knowledge base
          try {
            const kbRes = await fetch(`${API_BASE}/devices/${deviceId}/knowledge-base`);
            if (kbRes.ok) {
              setKnowledgeBase(await kbRes.json());
            }
          } catch (e) {
            console.log('Knowledge base not available:', e);
          }

          // Fetch sensor
          if (sensorId) {
            const sensorRes = await fetch(`${API_BASE}/devices/${deviceId}/sensors/${sensorId}`);
            if (!sensorRes.ok) throw new Error('Failed to fetch sensor');
            const sensorData = await sensorRes.json();
            setSensor(sensorData);

            // Fetch metrics for the sensor
            const now = new Date();
            const from = new Date(now.getTime() - 24 * 60 * 60 * 1000); // Last 24 hours
            const metricsRes = await fetch(
              `${API_BASE}/metrics/${sensorId}?from=${from.toISOString()}&to=${now.toISOString()}`
            );
            if (metricsRes.ok) {
              setMetrics(await metricsRes.json());
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [deviceId, sensorId]);

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading sensor details...</Text>
      </Stack>
    );
  }

  if (error || !device || !sensor) {
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
            <Text size="lg" fw={600}>Error Loading Sensor</Text>
            <Text size="sm" c="dimmed">{error || 'Sensor not found'}</Text>
          </Stack>
        </Card>
      </Stack>
    );
  }

  const latestMetric = metrics.length > 0 ? metrics[metrics.length - 1] : null;
  const avgValue = metrics.length > 0
    ? metrics.reduce((sum, m) => sum + m.value, 0) / metrics.length
    : 0;

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between" align="center">
        <Group gap="sm">
          <Button
            variant="subtle"
            leftSection={<ArrowLeft size={18} />}
            onClick={() => navigate('/')}
          >
            Back to Devices
          </Button>
        </Group>
      </Group>

      {/* Device and Sensor Info */}
      <Card withBorder p="md">
        <Stack gap="sm">
          <Group justify="space-between">
            <div>
              <Text size="sm" c="dimmed">Device</Text>
              <Title order={3}>{device.name}</Title>
            </div>
            <Badge variant="light" color="blue">{device.type}</Badge>
          </Group>
          <Group>
            <div style={{ flex: 1 }}>
              <Text size="xs" c="dimmed">Manufacturer</Text>
              <Text fw={500}>{device.metadata?.manufacturer || '-'}</Text>
            </div>
            <div style={{ flex: 1 }}>
              <Text size="xs" c="dimmed">Model</Text>
              <Text fw={500}>{device.metadata?.model || '-'}</Text>
            </div>
            <div style={{ flex: 1 }}>
              <Text size="xs" c="dimmed">Integration</Text>
              <Badge variant="outline">{device.integration}</Badge>
            </div>
          </Group>
        </Stack>
      </Card>

      {/* Sensor Details */}
      <Card withBorder p="md">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <div>
              <Title order={2}>{sensor.name}</Title>
              <Text size="sm" c="dimmed" mt="xs">{sensor.type} Sensor</Text>
            </div>
            <Badge variant="light" size="lg">
              {sensor.unit}
            </Badge>
          </Group>

          {/* Metrics Summary */}
          <Grid>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Paper p="md" withBorder>
                <Group gap="xs">
                  <Activity size={20} color="#228be6" />
                  <div>
                    <Text size="xs" c="dimmed">Current Value</Text>
                    <Text size="xl" fw={700}>
                      {latestMetric ? latestMetric.value.toFixed(2) : 'N/A'} {sensor.unit}
                    </Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Paper p="md" withBorder>
                <Group gap="xs">
                  <TrendingUp size={20} color="#40c057" />
                  <div>
                    <Text size="xs" c="dimmed">24h Average</Text>
                    <Text size="xl" fw={700}>
                      {avgValue.toFixed(2)} {sensor.unit}
                    </Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Paper p="md" withBorder>
                <Group gap="xs">
                  <Calendar size={20} color="#ffa94d" />
                  <div>
                    <Text size="xs" c="dimmed">Data Points</Text>
                    <Text size="xl" fw={700}>
                      {metrics.length}
                    </Text>
                  </div>
                </Group>
              </Paper>
            </Grid.Col>
          </Grid>
        </Stack>
      </Card>

      {/* Documentation Section */}
      <Card withBorder p="md">
        <Tabs defaultValue="info">
          <Tabs.List>
            <Tabs.Tab value="info">Sensor Information</Tabs.Tab>
            <Tabs.Tab value="docs">Device Documentation</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="info" pt="md">
            <Stack gap="md">
              <Group>
                <div style={{ flex: 1 }}>
                  <Text size="sm" c="dimmed">Sensor ID</Text>
                  <Text fw={500} size="sm" style={{ wordBreak: 'break-all' }}>{sensor.id}</Text>
                </div>
              </Group>
              <Group>
                <div style={{ flex: 1 }}>
                  <Text size="sm" c="dimmed">Created</Text>
                  <Text fw={500}>
                    {new Date(sensor.created_at).toLocaleString()}
                  </Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Text size="sm" c="dimmed">Last Updated</Text>
                  <Text fw={500}>
                    {new Date(sensor.updated_at).toLocaleString()}
                  </Text>
                </div>
              </Group>
              {Object.keys(sensor.metadata || {}).length > 0 && (
                <div>
                  <Text size="sm" c="dimmed" mb="xs">Metadata</Text>
                  <Stack gap="xs">
                    {Object.entries(sensor.metadata).map(([key, value]) => (
                      <Group key={key} justify="space-between">
                        <Text size="sm" c="dimmed">{key}</Text>
                        <Text size="sm">{value}</Text>
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
                    Device documentation ingestion status and details
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
                    <div>
                      <Text size="sm" fw={500}>Documentation Successfully Ingested</Text>
                      <Text size="xs" c="dimmed">
                        Ingested at {new Date(device.docs_ingested_at).toLocaleString()}
                      </Text>
                    </div>
                  </Group>
                </Paper>
              )}

              {!device.docs_ingested && (
                <Paper p="md" withBorder bg="gray.0">
                  <Text size="sm" c="dimmed">
                    Device documentation is awaiting ingestion. The system will automatically discover and process documentation for this device.
                  </Text>
                </Paper>
              )}

              <div>
                <Title order={5} mb="xs">About This Device</Title>
                <Text size="sm" c="dimmed">
                  {device.name} is a {device.type} device integrated via {device.integration}.
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
                  <Title order={5} mb="md">Knowledge Base Articles</Title>
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
      </Card>

      {/* Recent Metrics */}
      {metrics.length > 0 && (
        <Card withBorder p="md">
          <Title order={4} mb="md">Recent Data (Last 24 Hours)</Title>
          <Stack gap="xs" style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {metrics.slice(-10).reverse().map((metric, idx) => (
              <Group key={idx} justify="space-between">
                <Text size="sm" c="dimmed">
                  {new Date(metric.timestamp).toLocaleString()}
                </Text>
                <Text size="sm" fw={500}>
                  {metric.value.toFixed(2)} {sensor.unit}
                </Text>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
