import { useEffect, useState } from 'react';
import {
  Card,
  Text,
  Badge,
  Group,
  Stack,
  SimpleGrid,
  Loader,
  Box,
  Title,
  ThemeIcon,
} from '@mantine/core';
import {
  Server,
  Database,
  Activity,
  Radio,
  AlertCircle,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';

const API_BASE = 'http://localhost:8080';

interface ServiceStatus {
  name: string;
  status: string;
  url?: string;
  error?: string;
  details?: any;
  brokers_count?: number;
}

interface SystemStatus {
  timestamp: string;
  services: {
    ai_sidecar: ServiceStatus;
    prometheus: ServiceStatus;
    database: ServiceStatus;
    mqtt_discovery: ServiceStatus;
  };
  summary: {
    devices: number;
    open_incidents: number;
    total_incidents: number;
  };
}

function StatusBadge({ status }: { status: string }) {
  const getColor = () => {
    switch (status) {
      case 'healthy':
        return 'green';
      case 'unhealthy':
        return 'red';
      case 'unavailable':
        return 'gray';
      case 'initialized':
        return 'blue';
      case 'not_initialized':
        return 'yellow';
      default:
        return 'gray';
    }
  };

  const getIcon = () => {
    switch (status) {
      case 'healthy':
      case 'initialized':
        return <CheckCircle size={16} />;
      case 'unhealthy':
      case 'not_initialized':
        return <XCircle size={16} />;
      default:
        return <AlertCircle size={16} />;
    }
  };

  return (
    <Badge color={getColor()} leftSection={getIcon()} variant="light">
      {status}
    </Badge>
  );
}

function ServiceCard({ service, icon }: { service: ServiceStatus; icon: React.ReactNode }) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Group justify="space-between" mb="md">
        <Group>
          <ThemeIcon size="lg" variant="light" color="blue">
            {icon}
          </ThemeIcon>
          <div>
            <Text fw={500} size="lg">
              {service.name}
            </Text>
            {service.url && (
              <Text size="xs" c="dimmed">
                {service.url}
              </Text>
            )}
          </div>
        </Group>
        <StatusBadge status={service.status} />
      </Group>

      {service.error && (
        <Box p="xs" bg="red.1" style={{ borderRadius: 4 }}>
          <Text size="sm" c="red.9">
            {service.error}
          </Text>
        </Box>
      )}

      {service.details && (
        <Box p="xs" bg="gray.1" style={{ borderRadius: 4, marginTop: 8 }}>
          <Text size="xs" c="dimmed" ff="monospace">
            {JSON.stringify(service.details, null, 2)}
          </Text>
        </Box>
      )}

      {service.brokers_count !== undefined && (
        <Text size="sm" mt="sm" c="dimmed">
          Brokers discovered: {service.brokers_count}
        </Text>
      )}
    </Card>
  );
}

export function StatusView() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const initializeStatus = async () => {
    try {
      // Initialize status with empty services
      const initialStatus: SystemStatus = {
        timestamp: new Date().toISOString(),
        services: {
          ai_sidecar: { name: 'AI Sidecar', status: 'unavailable' },
          prometheus: { name: 'Prometheus', status: 'unavailable' },
          database: { name: 'Database', status: 'unavailable' },
          mqtt_discovery: { name: 'MQTT Discovery', status: 'unavailable' },
        },
        summary: {
          devices: 0,
          open_incidents: 0,
          total_incidents: 0,
        },
      };
      setStatus(initialStatus);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchServiceStatus = async (serviceName: keyof SystemStatus['services']) => {
    try {
      const response = await fetch(`${API_BASE}/api/status/${serviceName}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStatus(prev =>
        prev ? {
          ...prev,
          services: {
            ...prev.services,
            [serviceName]: {
              // Merge with existing service data to preserve name, url, etc.
              ...prev.services[serviceName],
              ...data
            }
          }
        } : null
      );
    } catch (err) {
      console.error(`Failed to fetch ${serviceName} status:`, err);
    }
  };

  useEffect(() => {
    initializeStatus();

    // Fetch all service statuses in parallel immediately
    Promise.all([
      fetchServiceStatus('ai_sidecar'),
      fetchServiceStatus('prometheus'),
      fetchServiceStatus('database')
    ]);

    // Then refresh them frequently
    const serviceInterval = setInterval(() => {
      Promise.all([
        fetchServiceStatus('ai_sidecar'),
        fetchServiceStatus('prometheus'),
        fetchServiceStatus('database')
      ]);
      setLastUpdate(new Date());
    }, 5000); // Every 5 seconds for individual services

    return () => {
      clearInterval(serviceInterval);
    };
  }, []);

  if (loading) {
    return (
      <Box style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Loader size="lg" />
      </Box>
    );
  }

  if (error) {
    return (
      <Card shadow="sm" padding="lg" radius="md" withBorder bg="red.1">
        <Group>
          <ThemeIcon color="red" size="lg">
            <XCircle />
          </ThemeIcon>
          <div>
            <Text fw={500} c="red.9">
              Failed to load system status
            </Text>
            <Text size="sm" c="red.7">
              {error}
            </Text>
          </div>
        </Group>
      </Card>
    );
  }

  if (!status) {
    return null;
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>System Status</Title>
        <Group gap="xs">
          <Clock size={16} />
          <Text size="sm" c="dimmed">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </Text>
        </Group>
      </Group>

      {/* Summary Cards */}
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Group>
            <ThemeIcon size="xl" variant="light" color="blue">
              <Activity />
            </ThemeIcon>
            <div>
              <Text size="xl" fw={700}>
                {status.summary.devices}
              </Text>
              <Text size="sm" c="dimmed">
                Devices
              </Text>
            </div>
          </Group>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Group>
            <ThemeIcon size="xl" variant="light" color="orange">
              <AlertCircle />
            </ThemeIcon>
            <div>
              <Text size="xl" fw={700}>
                {status.summary.open_incidents}
              </Text>
              <Text size="sm" c="dimmed">
                Open Incidents
              </Text>
            </div>
          </Group>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Group>
            <ThemeIcon size="xl" variant="light" color="gray">
              <CheckCircle />
            </ThemeIcon>
            <div>
              <Text size="xl" fw={700}>
                {status.summary.total_incidents}
              </Text>
              <Text size="sm" c="dimmed">
                Total Incidents
              </Text>
            </div>
          </Group>
        </Card>
      </SimpleGrid>

      {/* Service Status Cards */}
      <Title order={3} mt="md">
        Services
      </Title>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <ServiceCard service={status.services.ai_sidecar} icon={<Server />} />
        <ServiceCard service={status.services.prometheus} icon={<Activity />} />
        <ServiceCard service={status.services.database} icon={<Database />} />
        <ServiceCard service={status.services.mqtt_discovery} icon={<Radio />} />
      </SimpleGrid>
    </Stack>
  );
}
