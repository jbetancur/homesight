
import { useEffect, useState, useCallback, useRef } from 'react';
import { Table, Button, Badge, Text, Loader, Stack, Group, Title, Card, Paper, Alert } from '@mantine/core';
import { Check, AlertCircle, Plus, RefreshCw, Wifi } from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';

const API_BASE = 'http://localhost:8080/api';

export function DiscoveryView() {
  const [discovery, setDiscovery] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [onboardingId, setOnboardingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const devicesRef = useRef<any[]>([]);
  const discoveryRef = useRef<any[]>([]);

  const fetchDiscovery = async (useTestMode = true) => {
    const url = useTestMode ? `${API_BASE}/discovery?test=true` : `${API_BASE}/discovery`;
    const res = await fetch(url);
    const data = await res.json();
    const devices = data?.devices || [];
    setDiscovery(devices);
    discoveryRef.current = devices;
    return devices;
  };

  const fetchDevices = async () => {
    const res = await fetch(`${API_BASE}/devices`);
    const data = await res.json();
    const deviceList = data || [];
    setDevices(deviceList);
    devicesRef.current = deviceList;
    return deviceList;
  };

  useEffect(() => {
    Promise.all([fetchDiscovery(), fetchDevices()])
      .then(() => setLoading(false))
      .catch(() => {
        setError('Failed to load discovery data');
        setLoading(false);
      });
  }, []);

  // Listen for device_added events to update the list
  const handleEvent = useCallback((event: any) => {
    if (event.type === "device_added") {
      const exists = devicesRef.current.some(d => d.id === event.data.id);
      if (!exists) {
        const updated = [...devicesRef.current, event.data];
        devicesRef.current = updated;
        setDevices(updated);
      }
    } else if (event.type === "device_updated") {
      const updated = devicesRef.current.map(d => d.id === event.data.id ? event.data : d);
      devicesRef.current = updated;
      setDevices(updated);
    }
  }, []);
  useEventSubscription(handleEvent);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await Promise.all([fetchDiscovery(), fetchDevices()]);
    } catch (err) {
      setError('Failed to refresh discovery data');
    } finally {
      setRefreshing(false);
    }
  };

  const handleAddDevice = async (id: string) => {
    // Prevent multiple POSTs for the same device
    if (onboardingId) return;

    // Double-check not already onboarded
    const alreadyExists = devices.some(d => d.id === id);
    if (alreadyExists) {
      setError('Device already onboarded');
      setTimeout(() => setError(null), 3000);
      return;
    }

    setOnboardingId(id);
    setError(null);

    const device = discovery.find(d => d.id === id);
    if (!device) {
      setError('Device not found in discovery list');
      setOnboardingId(null);
      return;
    }

    // Map discovery fields to Device model
    const payload = {
      id: device.id,
      name: device.name || device.id,
      type: device.type || '',
      integration: device.integration || '',
      zone_id: device.zone_id || '',
      asset_id: device.asset_id || '',
      enabled: true,
      last_seen: new Date().toISOString(),
      metadata: {
        manufacturer: device.manufacturer || '',
        model: device.model || '',
        host: device.host || '',
        ...device.metadata
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    try {
      const res = await fetch(`${API_BASE}/devices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        // Refresh both lists to sync state
        await fetchDevices();
        await fetchDiscovery();
      } else {
        const errorText = await res.text();
        setError(`Failed to onboard device: ${errorText}`);
        console.error('Onboarding failed:', errorText);
      }
    } catch (err) {
      setError('Network error while onboarding device');
      console.error('Onboarding error:', err);
    } finally {
      setOnboardingId(null);
    }
  };

  // Filter out devices that are already onboarded (by id)
  // Use Set for O(1) lookup performance
  const deviceIds = new Set(devices.map((d: any) => d.id));
  const filteredDiscovery = discovery.filter(device => !deviceIds.has(device.id));

  const onboardedCount = devices.length;
  const availableCount = filteredDiscovery.length;

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading discovered devices...</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Device Discovery</Title>
          <Text size="sm" c="dimmed">Discover and onboard new devices on your network</Text>
        </div>
        <Button
          leftSection={<RefreshCw size={16} />}
          onClick={handleRefresh}
          loading={refreshing}
          variant="light"
        >
          Refresh
        </Button>
      </Group>

      <Group gap="md">
        <Paper p="md" withBorder style={{ flex: 1 }}>
          <Group gap="xs">
            <Wifi size={24} color="#228be6" />
            <div>
              <Text size="xl" fw={700}>{availableCount}</Text>
              <Text size="xs" c="dimmed">Available to Onboard</Text>
            </div>
          </Group>
        </Paper>

        <Paper p="md" withBorder style={{ flex: 1 }}>
          <Group gap="xs">
            <Check size={24} color="#40c057" />
            <div>
              <Text size="xl" fw={700}>{onboardedCount}</Text>
              <Text size="xs" c="dimmed">Already Onboarded</Text>
            </div>
          </Group>
        </Paper>
      </Group>

      {error && (
        <Alert color="red" title="Error" icon={<AlertCircle size={16} />} onClose={() => setError(null)} withCloseButton>
          {error}
        </Alert>
      )}

      {filteredDiscovery.length === 0 ? (
        <Card withBorder p="xl">
          <Stack align="center" gap="md">
            <Check size={48} color="#40c057" />
            <div style={{ textAlign: 'center' }}>
              <Text size="lg" fw={600}>All Devices Onboarded</Text>
              <Text size="sm" c="dimmed">No new devices discovered. Click refresh to scan again.</Text>
            </div>
          </Stack>
        </Card>
      ) : (
        <Card withBorder p={0}>
          <Table highlightOnHover striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Integration</Table.Th>
                <Table.Th>Host</Table.Th>
                <Table.Th>Manufacturer</Table.Th>
                <Table.Th>Model</Table.Th>
                <Table.Th style={{ textAlign: 'center' }}>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredDiscovery.map((device: any, idx: number) => (
                <Table.Tr key={device.id ? `${device.id}-${idx}` : idx}>
                  <Table.Td>
                    <Text fw={500}>{device.name || device.id}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color="blue">{device.type}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="outline">{device.integration}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">{device.host || '-'}</Text>
                  </Table.Td>
                  <Table.Td>{device.manufacturer || '-'}</Table.Td>
                  <Table.Td>{device.model || '-'}</Table.Td>
                  <Table.Td style={{ textAlign: 'center' }}>
                    <Button
                      onClick={() => handleAddDevice(device.id)}
                      color="blue"
                      size="xs"
                      leftSection={<Plus size={14} />}
                      loading={onboardingId === device.id}
                      disabled={onboardingId === device.id}
                    >
                      {onboardingId === device.id ? 'Adding...' : 'Add Device'}
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  );
}
