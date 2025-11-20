
import { useEffect, useState, useRef, useCallback } from 'react';
import { Table, Badge, Loader, Stack, Title, Text, Card, Group, Paper, Button, Modal, ActionIcon, Tooltip } from '@mantine/core';
import { Wifi, CheckCircle, Activity, Trash2 } from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';

const API_BASE = 'http://localhost:8080/api';

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

export function DevicesView() {
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [offboardingId, setOffboardingId] = useState<string | null>(null);
  const [confirmModal, setConfirmModal] = useState<{open: boolean, deviceId: string | null, deviceName: string}>({
    open: false,
    deviceId: null,
    deviceName: ''
  });
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
      updated = updated.map(d => d.id === event.data.id ? event.data : d);
      devicesRef.current = updated;
      setDevices(updated);
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

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading devices...</Text>
      </Stack>
    );
  }

  const onlineDevices = devices.filter(d => getDeviceStatus(d.last_seen).label === 'Online');
  const totalDevices = devices.length;

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Devices</Title>
          <Text size="sm" c="dimmed">Manage and monitor your connected devices</Text>
        </div>
      </Group>

      <Group gap="md">
        <Paper p="md" withBorder style={{ flex: 1 }}>
          <Group gap="xs">
            <Wifi size={24} color="#228be6" />
            <div>
              <Text size="xl" fw={700}>{totalDevices}</Text>
              <Text size="xs" c="dimmed">Total Devices</Text>
            </div>
          </Group>
        </Paper>

        <Paper p="md" withBorder style={{ flex: 1 }}>
          <Group gap="xs">
            <CheckCircle size={24} color="#40c057" />
            <div>
              <Text size="xl" fw={700}>{onlineDevices.length}</Text>
              <Text size="xs" c="dimmed">Online Now</Text>
            </div>
          </Group>
        </Paper>
      </Group>

      {devices.length === 0 ? (
        <Card withBorder p="xl">
          <Stack align="center" gap="md">
            <Wifi size={48} color="#868e96" />
            <div style={{ textAlign: 'center' }}>
              <Text size="lg" fw={600}>No Devices</Text>
              <Text size="sm" c="dimmed">Visit the Discovery page to onboard new devices</Text>
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
                <Table.Th>Manufacturer</Table.Th>
                <Table.Th>Model</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Last Seen</Table.Th>
                <Table.Th style={{ textAlign: 'center' }}>Actions</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {devices.map((device: any) => {
                const status = getDeviceStatus(device.last_seen);
                return (
                  <Table.Tr key={device.id}>
                    <Table.Td>
                      <Group gap="xs">
                        <Activity size={16} />
                        <Text fw={500}>{device.name}</Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="blue">{device.type}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="outline">{device.integration}</Badge>
                    </Table.Td>
                    <Table.Td>{device.metadata?.manufacturer || '-'}</Table.Td>
                    <Table.Td>{device.metadata?.model || '-'}</Table.Td>
                    <Table.Td>
                      <Badge color={status.color}>{status.label}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {new Date(device.last_seen).toLocaleString()}
                      </Text>
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'center' }}>
                      <Tooltip label="Offboard Device">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          onClick={() => setConfirmModal({
                            open: true,
                            deviceId: device.id,
                            deviceName: device.name
                          })}
                          loading={offboardingId === device.id}
                          disabled={offboardingId === device.id}
                        >
                          <Trash2 size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Card>
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
            This will remove the device from monitoring. You can re-onboard it later from the Discovery page if needed.
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
