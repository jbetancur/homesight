import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Paper, Text, Group, Stack, Progress, ThemeIcon, Badge, Box, RingProgress, Grid, Tooltip, Modal, Table, Button } from '@mantine/core';
import { Brain, TrendingUp, Activity, Zap, Target, Database, ExternalLink, AlertTriangle } from 'lucide-react';
import { API_BASE } from '../apiConfig';

interface ModelMaturity {
  status: string;
  update_count: number;
  clusters_detected?: number;
  // Real performance metrics
  mae?: number;
  rmse?: number;
  accuracy_pct?: number;
}

interface LearningVelocity {
  total_updates: number;
  actual_hours_active: number;
  updates_per_hour: number;
  data_quality_score: number;
  first_event_time?: string;
  last_event_time?: string;
}

interface DriftDetection {
  drift_detected: boolean;
  severity: number;
  error_window_size: number;
}

interface DeviceHealth {
  device_id: string;
  erratic_score: number;
  decayed_erratic_score: number;
  is_erratic: boolean;
  recent_event_count: number;
  anomaly_model_updates: number;
}

interface RiverML {
  comfort_model_updates: number;
  routine_model_updates: number;
  occupancy_model_updates: number;
  anomaly_models_active: number;
  baseline_models_active: number;
  frequency_models_active: number;
  total_model_updates: number;
  devices_tracked: number;
  erratic_device_count: number;
  erratic_devices: ErraticDevice[];
  model_maturity?: {
    comfort: ModelMaturity;
    routine: ModelMaturity;
    occupancy: ModelMaturity;
  };
  learning_velocity?: LearningVelocity;
  device_health?: DeviceHealth[];
  drift_detection?: {
    comfort_model: DriftDetection;
  };
}

interface FeedbackLearning {
  total_interactions: number;
  learning_rate: number;
  high_confidence_preferences: number;
}

interface ModelStats {
  river_ml?: RiverML;
  feedback_learning?: FeedbackLearning;
  // Fallback for direct properties (for backward compatibility)
  comfort_model_updates?: number;
  routine_model_updates?: number;
  occupancy_model_updates?: number;
  anomaly_models_active?: number;
  baseline_models_active?: number;
  frequency_models_active?: number;
  total_model_updates?: number;
  devices_tracked?: number;
  erratic_device_count?: number;
  model_maturity?: {
    comfort: ModelMaturity;
    routine: ModelMaturity;
    occupancy: ModelMaturity;
  };
  learning_velocity?: LearningVelocity;
  device_health?: DeviceHealth[];
  drift_detection?: {
    comfort_model: DriftDetection;
  };
}

interface ModelInfo {
  name: string;
  icon: any;
  color: string;
  updates: number;
  confidence: number;
  description: string;
}

interface ErraticDevice {
  device_id: string;
  erratic_score: number;
  is_erratic: boolean;
  recent_events_per_minute: number;
  trend: string;
}

export default function LearningProgressChart() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<ModelStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [erraticModalOpen, setErraticModalOpen] = useState(false);
  const [erraticDevices, setErraticDevices] = useState<ErraticDevice[]>([]);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10000); // Update every 10s
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/hsil/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to fetch HSIL stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchErraticDevices = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/hsil/erratic`);
      if (res.ok) {
        const data = await res.json();
        setErraticDevices(data.erratic_devices || []);
        setErraticModalOpen(true);
      }
    } catch (error) {
      console.error('Failed to fetch erratic devices:', error);
    }
  };

  const handleErraticBadgeClick = () => {
    fetchErraticDevices();
  };

  const handleDeviceClick = (deviceId: string) => {
    setErraticModalOpen(false);
    navigate(`/devices/${deviceId}/overview`);
  };

  const calculateConfidence = (updates: number, max: number = 1000): number => {
    return Math.min(100, (updates / max) * 100);
  };

  const getConfidenceColor = (confidence: number): string => {
    if (confidence >= 75) return 'green';
    if (confidence >= 50) return 'yellow';
    if (confidence >= 25) return 'orange';
    return 'red';
  };

  const getConfidenceLabel = (confidence: number): string => {
    if (confidence >= 75) return 'High';
    if (confidence >= 50) return 'Moderate';
    if (confidence >= 25) return 'Learning';
    return 'Initial';
  };

  if (loading || !stats) {
    return (
      <Paper p="md" withBorder>
        <Text size="sm" c="dimmed">
          Loading learning progress...
        </Text>
      </Paper>
    );
  }

  // Extract stats from river_ml nested object or use direct properties
  const mlStats = stats.river_ml || stats;

  // Use REAL accuracy instead of fake confidence
  const comfortAccuracy = mlStats?.model_maturity?.comfort?.accuracy_pct;
  const comfortMAE = mlStats?.model_maturity?.comfort?.mae;

  const models: ModelInfo[] = [
    {
      name: 'Comfort Model',
      icon: TrendingUp,
      color: 'blue',
      updates: mlStats?.comfort_model_updates || 0,
      // Use real accuracy if available, otherwise fall back to update-based progress
      confidence: comfortAccuracy !== null && comfortAccuracy !== undefined
        ? comfortAccuracy
        : calculateConfidence(mlStats?.comfort_model_updates || 0),
      description: comfortMAE
        ? `Prediction error: ±${comfortMAE.toFixed(1)}°F`
        : 'Learns preferred temperature & humidity',
    },
    {
      name: 'Routine Model',
      icon: Activity,
      color: 'grape',
      updates: mlStats?.routine_model_updates || 0,
      confidence: calculateConfidence(mlStats?.routine_model_updates || 0),
      description: `${mlStats?.model_maturity?.routine?.clusters_detected || 0} patterns detected`,
    },
    {
      name: 'Anomaly Detection',
      icon: Zap,
      color: 'red',
      updates: mlStats?.anomaly_models_active || 0,
      confidence: calculateConfidence(mlStats?.anomaly_models_active || 0, 20),
      description: `Monitoring ${mlStats?.anomaly_models_active || 0} devices`,
    },
    {
      name: 'Baseline Tracking',
      icon: Target,
      color: 'teal',
      updates: mlStats?.baseline_models_active || 0,
      confidence: calculateConfidence(mlStats?.baseline_models_active || 0, 50),
      description: `Tracking ${mlStats?.baseline_models_active || 0} metrics`,
    },
  ];

  // Use comfort accuracy for overall if available, otherwise use update-based
  const overallConfidence = comfortAccuracy !== null && comfortAccuracy !== undefined
    ? comfortAccuracy
    : calculateConfidence(mlStats?.total_model_updates || 0, 5000);

  return (
    <Stack gap="lg">
      {/* Overall Progress Ring */}
      <Paper p="xl" withBorder style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
        <Group justify="space-between" align="flex-start">
          <Stack gap="xs">
            <Group gap="xs">
              <ThemeIcon size="xl" radius="xl" variant="light" color="white">
                <Brain size={28} />
              </ThemeIcon>
              <div>
                <Text size="xl" fw={700} c="white">
                  Learning Progress
                </Text>
                <Text size="sm" c="rgba(255,255,255,0.8)">
                  AI models improving over time
                </Text>
              </div>
            </Group>

            <Group gap="xl" mt="md">
              <Box>
                <Text size="xs" c="rgba(255,255,255,0.8)">
                  Total Updates
                </Text>
                <Text size="xl" fw={700} c="white">
                  {(mlStats?.total_model_updates || 0).toLocaleString()}
                </Text>
              </Box>
              <Box>
                <Text size="xs" c="rgba(255,255,255,0.8)">
                  Devices Tracked
                </Text>
                <Text size="xl" fw={700} c="white">
                  {mlStats?.devices_tracked || 0}
                </Text>
              </Box>
              {(mlStats?.erratic_device_count || 0) > 0 && (
                <Tooltip label="Click to view erratic devices">
                  <Box
                    style={{ cursor: 'pointer' }}
                    onClick={handleErraticBadgeClick}
                  >
                    <Text size="xs" c="rgba(255,255,255,0.8)">
                      Erratic Devices
                    </Text>
                    <Badge size="lg" color="red" variant="filled" style={{ cursor: 'pointer' }}>
                      {mlStats.erratic_device_count} <ExternalLink size={12} style={{ marginLeft: 4 }} />
                    </Badge>
                  </Box>
                </Tooltip>
              )}
            </Group>
          </Stack>

          <RingProgress
            size={140}
            thickness={12}
            sections={[
              {
                value: overallConfidence,
                color: 'white',
              },
            ]}
            label={
              <Box style={{ textAlign: 'center' }}>
                <Text size="xl" fw={700} c="white">
                  {overallConfidence.toFixed(0)}%
                </Text>
                <Text size="xs" c="rgba(255,255,255,0.8)">
                  Confidence
                </Text>
              </Box>
            }
          />
        </Group>
      </Paper>

      {/* Individual Model Progress */}
      <Grid>
        {models.map((model, idx) => {
          const Icon = model.icon;
          const confidence = model.confidence;
          const confidenceColor = getConfidenceColor(confidence);
          const confidenceLabel = getConfidenceLabel(confidence);

          return (
            <Grid.Col key={idx} span={{ base: 12, sm: 6 }}>
              <Paper p="md" withBorder h="100%">
                <Stack gap="md">
                  <Group justify="space-between">
                    <Group gap="sm">
                      <ThemeIcon size="lg" variant="light" color={model.color}>
                        <Icon size={20} />
                      </ThemeIcon>
                      <div>
                        <Text size="sm" fw={600}>
                          {model.name}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {model.description}
                        </Text>
                      </div>
                    </Group>

                    <Badge color={confidenceColor} variant="light">
                      {confidenceLabel}
                    </Badge>
                  </Group>

                  <Stack gap="xs">
                    <Group justify="space-between">
                      <Text size="xs" c="dimmed">
                        Training Progress
                      </Text>
                      <Text size="xs" fw={600} c={confidenceColor}>
                        {confidence.toFixed(1)}%
                      </Text>
                    </Group>
                    <Progress
                      value={confidence}
                      color={confidenceColor}
                      size="lg"
                      radius="xl"
                      animated={confidence < 100}
                    />
                    <Group justify="space-between" mt={4}>
                      <Group gap={4}>
                        <Database size={12} />
                        <Text size="xs" c="dimmed">
                          {model.updates.toLocaleString()} updates
                        </Text>
                      </Group>
                      {confidence < 100 && (
                        <Text size="xs" c="dimmed" fs="italic">
                          Still learning...
                        </Text>
                      )}
                    </Group>
                  </Stack>
                </Stack>
              </Paper>
            </Grid.Col>
          );
        })}
      </Grid>

      {/* Model Maturity & Learning Velocity */}
      {mlStats?.model_maturity && mlStats?.learning_velocity && (
        <Grid>
          {/* Model Maturity Card */}
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Paper p="md" withBorder h="100%">
              <Group gap="xs" mb="md">
                <ThemeIcon size="sm" variant="light" color="violet">
                  <Target size={14} />
                </ThemeIcon>
                <Text size="sm" fw={600}>
                  Model Maturity
                </Text>
              </Group>
              <Stack gap="sm">
                <Box>
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">Comfort Model</Text>
                    <Group gap={4}>
                      <Badge
                        size="sm"
                        color={
                          mlStats.model_maturity.comfort.status === 'mature' ? 'green' :
                          mlStats.model_maturity.comfort.status === 'developing' ? 'yellow' :
                          'gray'
                        }
                      >
                        {mlStats.model_maturity.comfort.status}
                      </Badge>
                      {mlStats.model_maturity.comfort.accuracy_pct !== null &&
                       mlStats.model_maturity.comfort.accuracy_pct !== undefined && (
                        <Badge size="sm" color="blue">
                          {mlStats.model_maturity.comfort.accuracy_pct.toFixed(0)}% accurate
                        </Badge>
                      )}
                    </Group>
                  </Group>
                  <Progress
                    value={mlStats.model_maturity.comfort.accuracy_pct ??
                           (mlStats.model_maturity.comfort.update_count / 1000 * 100)}
                    size="sm"
                    color={
                      mlStats.model_maturity.comfort.status === 'mature' ? 'green' :
                      mlStats.model_maturity.comfort.status === 'developing' ? 'yellow' :
                      'gray'
                    }
                  />
                  {mlStats.model_maturity.comfort.mae !== null &&
                   mlStats.model_maturity.comfort.mae !== undefined && (
                    <Text size="xs" c="dimmed" mt={4}>
                      Error: ±{mlStats.model_maturity.comfort.mae.toFixed(1)}°F MAE,
                      {mlStats.model_maturity.comfort.rmse?.toFixed(1)}°F RMSE
                    </Text>
                  )}
                </Box>

                <Box>
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">Routine Model</Text>
                    <Badge
                      size="sm"
                      color={
                        mlStats.model_maturity.routine.status === 'mature' ? 'green' :
                        mlStats.model_maturity.routine.status === 'developing' ? 'yellow' :
                        'gray'
                      }
                    >
                      {mlStats.model_maturity.routine.status}
                      {mlStats.model_maturity.routine.clusters_detected ?
                        ` (${mlStats.model_maturity.routine.clusters_detected} clusters)` :
                        ''
                      }
                    </Badge>
                  </Group>
                  <Progress
                    value={(mlStats.model_maturity.routine.update_count / 1000 * 100)}
                    size="sm"
                    color={
                      mlStats.model_maturity.routine.status === 'mature' ? 'green' :
                      mlStats.model_maturity.routine.status === 'developing' ? 'yellow' :
                      'gray'
                    }
                  />
                </Box>

                <Box>
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">Occupancy Model</Text>
                    <Badge
                      size="sm"
                      color={
                        mlStats.model_maturity.occupancy.status === 'mature' ? 'green' :
                        mlStats.model_maturity.occupancy.status === 'developing' ? 'yellow' :
                        'gray'
                      }
                    >
                      {mlStats.model_maturity.occupancy.status}
                    </Badge>
                  </Group>
                  <Progress
                    value={(mlStats.model_maturity.occupancy.update_count / 1000 * 100)}
                    size="sm"
                    color={
                      mlStats.model_maturity.occupancy.status === 'mature' ? 'green' :
                      mlStats.model_maturity.occupancy.status === 'developing' ? 'yellow' :
                      'gray'
                    }
                  />
                </Box>
              </Stack>
            </Paper>
          </Grid.Col>

          {/* Learning Velocity Card */}
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Paper p="md" withBorder h="100%">
              <Group gap="xs" mb="md">
                <ThemeIcon size="sm" variant="light" color="cyan">
                  <TrendingUp size={14} />
                </ThemeIcon>
                <Text size="sm" fw={600}>
                  Learning Velocity
                </Text>
              </Group>
              <Stack gap="md">
                <Group justify="space-between">
                  <Text size="xs" c="dimmed">Updates/Hour</Text>
                  <Text size="sm" fw={600}>
                    {(mlStats.learning_velocity.updates_per_hour ?? 0).toFixed(1)}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="xs" c="dimmed">Hours Active</Text>
                  <Text size="sm" fw={600}>
                    {(mlStats.learning_velocity.actual_hours_active ?? 0).toFixed(1)}h
                  </Text>
                </Group>
                <Box>
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">Data Quality</Text>
                    <Text size="xs" fw={600}>
                      {(mlStats.learning_velocity.data_quality_score * 100).toFixed(0)}%
                    </Text>
                  </Group>
                  <Progress
                    value={mlStats.learning_velocity.data_quality_score * 100}
                    size="sm"
                    color={
                      mlStats.learning_velocity.data_quality_score > 0.7 ? 'green' :
                      mlStats.learning_velocity.data_quality_score > 0.4 ? 'yellow' :
                      'orange'
                    }
                  />
                </Box>
              </Stack>
            </Paper>
          </Grid.Col>
        </Grid>
      )}

      {/* Feedback Learning Stats */}
      {stats?.feedback_learning && stats.feedback_learning.total_interactions > 0 && (
        <Paper p="md" withBorder>
          <Group gap="xs" mb="md">
            <ThemeIcon size="sm" variant="light" color="pink">
              <Brain size={14} />
            </ThemeIcon>
            <Text size="sm" fw={600}>
              User Feedback Learning
            </Text>
          </Group>
          <Grid>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Box ta="center">
                <Text size="xl" fw={700} c="pink">
                  {stats.feedback_learning.total_interactions}
                </Text>
                <Text size="xs" c="dimmed">
                  Total Interactions
                </Text>
              </Box>
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Box ta="center">
                <Text size="xl" fw={700} c="pink">
                  {(stats.feedback_learning.learning_rate * 100).toFixed(1)}%
                </Text>
                <Text size="xs" c="dimmed">
                  Learning Rate
                </Text>
              </Box>
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Box ta="center">
                <Text size="xl" fw={700} c="pink">
                  {stats.feedback_learning.high_confidence_preferences}
                </Text>
                <Text size="xs" c="dimmed">
                  High Confidence Prefs
                </Text>
              </Box>
            </Grid.Col>
          </Grid>
        </Paper>
      )}

      {/* Model Drift Alert */}
      {mlStats?.drift_detection?.comfort_model?.drift_detected && (
        <Paper p="md" withBorder style={{ borderLeft: '4px solid var(--mantine-color-red-6)', backgroundColor: 'rgba(255, 107, 107, 0.1)' }}>
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="red">
              <AlertTriangle size={14} />
            </ThemeIcon>
            <Text size="sm" fw={600} c="red">
              Model Drift Detected
            </Text>
          </Group>
          <Stack gap="xs">
            <Text size="sm">
              The Comfort Model's prediction accuracy has degraded recently (severity: {(mlStats.drift_detection.comfort_model.severity * 100).toFixed(0)}%).
              This may indicate changing patterns in your home or sensor calibration issues.
            </Text>
            <Text size="xs" c="dimmed">
              Recent prediction errors are {((mlStats.drift_detection.comfort_model.severity + 1) * 100).toFixed(0)}% higher than baseline.
              The model will continue learning to adapt to new patterns.
            </Text>
          </Stack>
        </Paper>
      )}

      {/* Learning Insights */}
      <Paper p="md" withBorder style={{ borderLeft: '4px solid var(--mantine-color-indigo-6)' }}>
        <Group gap="xs" mb="sm">
          <ThemeIcon size="sm" variant="light" color="indigo">
            <Brain size={14} />
          </ThemeIcon>
          <Text size="sm" fw={600}>
            Learning Insights
          </Text>
        </Group>
        <Stack gap="xs">
          {comfortAccuracy !== null && comfortAccuracy !== undefined ? (
            <Text size="sm" c="dimmed">
              📊 Comfort Model: {comfortAccuracy.toFixed(0)}% accurate (±{comfortMAE?.toFixed(1)}°F average error)
            </Text>
          ) : overallConfidence < 25 ? (
            <Text size="sm" c="dimmed">
              🌱 Early learning phase - AI is gathering baseline data from your home
            </Text>
          ) : overallConfidence >= 25 && overallConfidence < 50 ? (
            <Text size="sm" c="dimmed">
              📊 Pattern recognition phase - AI is identifying routines and preferences
            </Text>
          ) : overallConfidence >= 50 && overallConfidence < 75 ? (
            <Text size="sm" c="dimmed">
              🎯 Optimization phase - AI is refining predictions and improving accuracy
            </Text>
          ) : (
            <Text size="sm" c="dimmed">
              ✨ Mature learning - AI has validated prediction accuracy
            </Text>
          )}

          {(mlStats?.erratic_device_count || 0) > 0 && (
            <Text
              size="sm"
              c="orange"
              style={{ cursor: 'pointer' }}
              onClick={handleErraticBadgeClick}
            >
              ⚠️ {mlStats?.erratic_device_count} device{(mlStats?.erratic_device_count || 0) > 1 ? 's' : ''} showing
              unusual behavior - <span style={{ textDecoration: 'underline' }}>click to view</span>
            </Text>
          )}

          {mlStats?.learning_velocity?.first_event_time && (
            <Text size="xs" c="dimmed">
              System active for {(mlStats.learning_velocity.actual_hours_active ?? 0).toFixed(1)} hours
              ({(mlStats.learning_velocity.updates_per_hour ?? 0).toFixed(0)} updates/hour)
            </Text>
          )}
        </Stack>
      </Paper>

      {/* Erratic Devices Modal */}
      <Modal
        opened={erraticModalOpen}
        onClose={() => setErraticModalOpen(false)}
        title={
          <Group gap="sm">
            <AlertTriangle size={20} color="#fd7e14" />
            <Text fw={600}>Devices Acting Unusual</Text>
          </Group>
        }
        size="lg"
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            These devices have been showing unusual activity patterns. Click on a device to view more details and incident history.
          </Text>

          {erraticDevices.length === 0 ? (
            <Text size="sm" c="dimmed" ta="center" py="xl">
              No erratic devices found at this time.
            </Text>
          ) : (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Device</Table.Th>
                  <Table.Th>Activity Score</Table.Th>
                  <Table.Th>Events/Min</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {erraticDevices.map((device) => (
                  <Table.Tr
                    key={device.device_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleDeviceClick(device.device_id)}
                  >
                    <Table.Td>
                      <Text fw={500}>{device.device_id}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={device.erratic_score > 0.7 ? 'red' : 'orange'}>
                        {(device.erratic_score * 100).toFixed(0)}%
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{device.recent_events_per_minute}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={device.is_erratic ? 'red' : 'yellow'} variant="light">
                        {device.is_erratic ? 'Active Issue' : 'Monitoring'}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="light"
                        rightSection={<ExternalLink size={14} />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeviceClick(device.device_id);
                        }}
                      >
                        View
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      </Modal>
    </Stack>
  );
}
