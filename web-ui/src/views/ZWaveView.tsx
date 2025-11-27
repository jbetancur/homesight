import { useEffect, useState, useCallback } from 'react';
import {
  Button, Badge, Text, Loader, Stack, Group, Title, Card, Paper,
  Modal, Alert, Progress, ActionIcon, Tooltip, Table
} from '@mantine/core';
import {
  Radio, Plus, RefreshCw, Trash2, AlertCircle, CheckCircle,
  Wifi, WifiOff, Activity, Shield, Battery, Zap
} from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;

interface ZWaveNode {
  nodeId: number;
  ready: boolean;
  status: number;
  deviceConfig: {
    manufacturer: string;
    label: string;
    description: string;
  };
  security?: string;
  firmwareVersion?: string;
  isListening: boolean;
  commandClasses: Record<number, any>;
}

interface ZWaveController {
  home_id: string;
  connected: boolean;
  ready: boolean;
  controller: any;
}

export function ZWaveView() {
  const [controller, setController] = useState<ZWaveController | null>(null);
  const [nodes, setNodes] = useState<ZWaveNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pairing modal state
  const [pairingModalOpen, setPairingModalOpen] = useState(false);
  const [pairingStatus, setPairingStatus] = useState<'idle' | 'pairing' | 'success' | 'failed'>('idle');
  const [pairingMessage, setPairingMessage] = useState('');
  const [pairingProgress, setPairingProgress] = useState(0);

  // Exclusion modal state
  const [exclusionModalOpen, setExclusionModalOpen] = useState(false);
  const [exclusionStatus, setExclusionStatus] = useState<'idle' | 'excluding' | 'success' | 'failed'>('idle');
  const [exclusionMessage, setExclusionMessage] = useState('');

  // Fetch controller status
  const fetchController = async () => {
    try {
      const res = await fetch(`${API_BASE}/zwave/controller`);
      if (!res.ok) {
        throw new Error('Z-Wave controller not available');
      }
      const data = await res.json();
      setController(data);
      setError(null);
    } catch (err: any) {
      setError(err.message);
      setController(null);
    }
  };

  // Fetch Z-Wave nodes
  const fetchNodes = async () => {
    try {
      const res = await fetch(`${API_BASE}/zwave/nodes`);
      if (!res.ok) {
        throw new Error('Failed to fetch Z-Wave nodes');
      }
      const data = await res.json();
      setNodes(data || []);
    } catch (err: any) {
      console.error('Failed to fetch nodes:', err);
    }
  };

  // Initial load
  useEffect(() => {
    Promise.all([fetchController(), fetchNodes()])
      .finally(() => setLoading(false));
  }, []);

  // Handle real-time events
  const handleEvent = useCallback((event: any) => {
    if (event.type === 'device_added' && event.data.integration === 'zwave') {
      // New Z-Wave device added
      fetchNodes();
      if (pairingStatus === 'pairing') {
        setPairingStatus('success');
        setPairingMessage(`Successfully paired: ${event.data.name}`);
        setPairingProgress(100);
        setTimeout(() => {
          setPairingModalOpen(false);
          setPairingStatus('idle');
        }, 2000);
      }
    } else if (event.type === 'device_removed' && event.data.integration === 'zwave') {
      // Z-Wave device removed
      fetchNodes();
      if (exclusionStatus === 'excluding') {
        setExclusionStatus('success');
        setExclusionMessage(`Successfully removed device`);
        setTimeout(() => {
          setExclusionModalOpen(false);
          setExclusionStatus('idle');
        }, 2000);
      }
    }
  }, [pairingStatus, exclusionStatus]);

  useEventSubscription(handleEvent);

  // Start device pairing
  const startPairing = async () => {
    setPairingStatus('pairing');
    setPairingMessage('Waiting for device...');
    setPairingProgress(0);

    try {
      const res = await fetch(`${API_BASE}/zwave/inclusion/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: 'Security_S2' }),
      });

      if (!res.ok) {
        throw new Error('Failed to start pairing');
      }

      const data = await res.json();
      setPairingMessage(data.message || 'Press the button on your Z-Wave device to pair');

      // Simulate progress while waiting
      let progress = 0;
      const interval = setInterval(() => {
        progress += 5;
        if (progress <= 90) {
          setPairingProgress(progress);
        } else {
          clearInterval(interval);
        }
      }, 1000);

      // Auto-timeout after 60 seconds
      setTimeout(() => {
        if (pairingStatus === 'pairing') {
          clearInterval(interval);
          stopPairing();
          setPairingStatus('failed');
          setPairingMessage('Pairing timeout - no device found');
        }
      }, 60000);

    } catch (err: any) {
      setPairingStatus('failed');
      setPairingMessage(err.message);
    }
  };

  // Stop device pairing
  const stopPairing = async () => {
    try {
      await fetch(`${API_BASE}/zwave/inclusion/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop pairing:', err);
    }
    setPairingModalOpen(false);
    setPairingStatus('idle');
  };

  // Start device exclusion
  const startExclusion = async () => {
    setExclusionStatus('excluding');
    setExclusionMessage('Waiting for device...');

    try {
      const res = await fetch(`${API_BASE}/zwave/exclusion/start`, {
        method: 'POST',
      });

      if (!res.ok) {
        throw new Error('Failed to start exclusion');
      }

      const data = await res.json();
      setExclusionMessage(data.message || 'Press the button on your Z-Wave device to remove it');

      // Auto-timeout after 60 seconds
      setTimeout(() => {
        if (exclusionStatus === 'excluding') {
          stopExclusion();
          setExclusionStatus('failed');
          setExclusionMessage('Exclusion timeout - no device found');
        }
      }, 60000);

    } catch (err: any) {
      setExclusionStatus('failed');
      setExclusionMessage(err.message);
    }
  };

  // Stop device exclusion
  const stopExclusion = async () => {
    try {
      await fetch(`${API_BASE}/zwave/exclusion/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop exclusion:', err);
    }
    setExclusionModalOpen(false);
    setExclusionStatus('idle');
  };

  // Heal node
  const healNode = async (nodeId: number) => {
    try {
      await fetch(`${API_BASE}/zwave/heal?node_id=${nodeId}`, { method: 'POST' });
      alert(`Network heal started for node ${nodeId}`);
    } catch (err) {
      alert('Failed to start network heal');
    }
  };

  // Remove failed node
  const removeFailedNode = async (nodeId: number) => {
    if (!confirm(`Remove failed node ${nodeId}? This cannot be undone.`)) {
      return;
    }

    try {
      await fetch(`${API_BASE}/zwave/remove-failed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId }),
      });
      alert(`Node ${nodeId} removed`);
      fetchNodes();
    } catch (err) {
      alert('Failed to remove node');
    }
  };

  // Get security badge
  const getSecurityBadge = (security?: string) => {
    if (!security) return <Badge size="xs" color="gray">None</Badge>;

    if (security.includes('S2')) {
      return (
        <Badge size="xs" color="green" leftSection={<Shield size={12} />}>
          S2
        </Badge>
      );
    }
    if (security.includes('S0')) {
      return (
        <Badge size="xs" color="yellow" leftSection={<Shield size={12} />}>
          S0
        </Badge>
      );
    }
    return <Badge size="xs" color="gray">{security}</Badge>;
  };

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: 400 }}>
        <Loader size="lg" />
        <Text>Loading Z-Wave controller...</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group>
          <Radio size={32} color="#228be6" />
          <div>
            <Title order={2}>Z-Wave Controller</Title>
            <Text size="sm" c="dimmed">Manage Z-Wave devices and network</Text>
          </div>
        </Group>
        <Button
          leftSection={<RefreshCw size={16} />}
          variant="light"
          onClick={() => {
            setLoading(true);
            Promise.all([fetchController(), fetchNodes()]).finally(() => setLoading(false));
          }}
        >
          Refresh
        </Button>
      </Group>

      {error && (
        <Alert icon={<AlertCircle size={16} />} color="red" title="Connection Error">
          {error}
        </Alert>
      )}

      {/* Controller Status Card */}
      <Card shadow="sm" padding="lg" radius="md" withBorder>
        <Stack gap="md">
          <Group justify="space-between">
            <Text fw={600} size="lg">Controller Status</Text>
            {controller?.connected ? (
              <Badge color="green" leftSection={<Wifi size={12} />}>Connected</Badge>
            ) : (
              <Badge color="red" leftSection={<WifiOff size={12} />}>Disconnected</Badge>
            )}
          </Group>

          {controller && (
            <Paper p="md" withBorder>
              <Stack gap="xs">
                <Group>
                  <Text size="sm" fw={500}>Home ID:</Text>
                  <Text size="sm" c="dimmed" ff="monospace">{controller.home_id}</Text>
                </Group>
                <Group>
                  <Text size="sm" fw={500}>Status:</Text>
                  <Badge size="sm" color={controller.ready ? 'green' : 'yellow'}>
                    {controller.ready ? 'Ready' : 'Initializing'}
                  </Badge>
                </Group>
                <Group>
                  <Text size="sm" fw={500}>Devices:</Text>
                  <Text size="sm" c="dimmed">{nodes.length} paired</Text>
                </Group>
              </Stack>
            </Paper>
          )}

          <Group>
            <Button
              leftSection={<Plus size={16} />}
              onClick={() => setPairingModalOpen(true)}
              disabled={!controller?.connected}
            >
              Add Device
            </Button>
            <Button
              leftSection={<Trash2 size={16} />}
              variant="light"
              color="red"
              onClick={() => setExclusionModalOpen(true)}
              disabled={!controller?.connected}
            >
              Remove Device
            </Button>
          </Group>
        </Stack>
      </Card>

      {/* Z-Wave Nodes List */}
      <Card shadow="sm" padding="lg" radius="md" withBorder>
        <Stack gap="md">
          <Text fw={600} size="lg">Paired Devices ({nodes.length})</Text>

          {nodes.length === 0 ? (
            <Paper p="xl" withBorder style={{ textAlign: 'center' }}>
              <Stack align="center" gap="sm">
                <Radio size={48} color="#ccc" />
                <Text c="dimmed">No Z-Wave devices paired yet</Text>
                <Button
                  leftSection={<Plus size={16} />}
                  onClick={() => setPairingModalOpen(true)}
                  disabled={!controller?.connected}
                >
                  Add Your First Device
                </Button>
              </Stack>
            </Paper>
          ) : (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Node ID</Table.Th>
                  <Table.Th>Device</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Security</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {nodes.map((node) => (
                  <Table.Tr key={node.nodeId}>
                    <Table.Td>
                      <Badge variant="light">{node.nodeId}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text size="sm" fw={500}>
                          {node.deviceConfig?.label || `Node ${node.nodeId}`}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {node.deviceConfig?.manufacturer || 'Unknown'}
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      {node.ready ? (
                        <Badge color="green" size="sm" leftSection={<CheckCircle size={12} />}>
                          Ready
                        </Badge>
                      ) : (
                        <Badge color="yellow" size="sm" leftSection={<Activity size={12} />}>
                          Interviewing
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>{getSecurityBadge(node.security)}</Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        {node.isListening ? (
                          <Tooltip label="Always listening">
                            <Zap size={14} color="#40c057" />
                          </Tooltip>
                        ) : (
                          <Tooltip label="Battery powered">
                            <Battery size={14} color="#fd7e14" />
                          </Tooltip>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Tooltip label="Heal network">
                          <ActionIcon
                            variant="light"
                            size="sm"
                            onClick={() => healNode(node.nodeId)}
                          >
                            <Activity size={14} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Remove failed node">
                          <ActionIcon
                            variant="light"
                            color="red"
                            size="sm"
                            onClick={() => removeFailedNode(node.nodeId)}
                          >
                            <Trash2 size={14} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      </Card>

      {/* Pairing Modal */}
      <Modal
        opened={pairingModalOpen}
        onClose={() => {
          if (pairingStatus === 'pairing') {
            stopPairing();
          } else {
            setPairingModalOpen(false);
            setPairingStatus('idle');
          }
        }}
        title="Add Z-Wave Device"
        size="md"
      >
        <Stack gap="md">
          {pairingStatus === 'idle' && (
            <>
              <Alert icon={<Radio size={16} />} color="blue">
                Put your Z-Wave device in pairing mode, then click "Start Pairing" below.
                Most devices enter pairing mode by pressing a button 3 times.
              </Alert>
              <Button onClick={startPairing} fullWidth>
                Start Pairing
              </Button>
            </>
          )}

          {pairingStatus === 'pairing' && (
            <>
              <Stack align="center" gap="md">
                <Loader size="lg" />
                <Text fw={500}>{pairingMessage}</Text>
                <Progress value={pairingProgress} style={{ width: '100%' }} animated />
              </Stack>
              <Button onClick={stopPairing} variant="light" fullWidth>
                Cancel
              </Button>
            </>
          )}

          {pairingStatus === 'success' && (
            <Alert icon={<CheckCircle size={16} />} color="green">
              {pairingMessage}
            </Alert>
          )}

          {pairingStatus === 'failed' && (
            <>
              <Alert icon={<AlertCircle size={16} />} color="red">
                {pairingMessage}
              </Alert>
              <Button onClick={() => setPairingStatus('idle')} fullWidth>
                Try Again
              </Button>
            </>
          )}
        </Stack>
      </Modal>

      {/* Exclusion Modal */}
      <Modal
        opened={exclusionModalOpen}
        onClose={() => {
          if (exclusionStatus === 'excluding') {
            stopExclusion();
          } else {
            setExclusionModalOpen(false);
            setExclusionStatus('idle');
          }
        }}
        title="Remove Z-Wave Device"
        size="md"
      >
        <Stack gap="md">
          {exclusionStatus === 'idle' && (
            <>
              <Alert icon={<AlertCircle size={16} />} color="orange">
                Put your Z-Wave device in exclusion mode, then click "Start Exclusion" below.
                This will remove the device from your network.
              </Alert>
              <Button onClick={startExclusion} color="red" fullWidth>
                Start Exclusion
              </Button>
            </>
          )}

          {exclusionStatus === 'excluding' && (
            <>
              <Stack align="center" gap="md">
                <Loader size="lg" />
                <Text fw={500}>{exclusionMessage}</Text>
              </Stack>
              <Button onClick={stopExclusion} variant="light" fullWidth>
                Cancel
              </Button>
            </>
          )}

          {exclusionStatus === 'success' && (
            <Alert icon={<CheckCircle size={16} />} color="green">
              {exclusionMessage}
            </Alert>
          )}

          {exclusionStatus === 'failed' && (
            <>
              <Alert icon={<AlertCircle size={16} />} color="red">
                {exclusionMessage}
              </Alert>
              <Button onClick={() => setExclusionStatus('idle')} fullWidth>
                Try Again
              </Button>
            </>
          )}
        </Stack>
      </Modal>
    </Stack>
  );
}
