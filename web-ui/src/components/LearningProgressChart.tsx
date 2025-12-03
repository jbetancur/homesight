import { useEffect, useState } from 'react';
import { Paper, Text, Group, Stack, Progress, ThemeIcon, Badge, Box, RingProgress, Grid } from '@mantine/core';
import { Brain, TrendingUp, Activity, Zap, Target, Database } from 'lucide-react';
import { API_BASE } from '../apiConfig';

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
  erratic_devices: any[];
}

interface ModelStats {
  river_ml?: RiverML;
  // Fallback for direct properties
  comfort_model_updates?: number;
  routine_model_updates?: number;
  occupancy_model_updates?: number;
  anomaly_models_active?: number;
  baseline_models_active?: number;
  frequency_models_active?: number;
  total_model_updates?: number;
  devices_tracked?: number;
  erratic_device_count?: number;
}

interface ModelInfo {
  name: string;
  icon: any;
  color: string;
  updates: number;
  confidence: number;
  description: string;
}

export default function LearningProgressChart() {
  const [stats, setStats] = useState<ModelStats | null>(null);
  const [loading, setLoading] = useState(true);

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

  const models: ModelInfo[] = [
    {
      name: 'Comfort Model',
      icon: TrendingUp,
      color: 'blue',
      updates: mlStats?.comfort_model_updates || 0,
      confidence: calculateConfidence(mlStats?.comfort_model_updates || 0),
      description: 'Learns preferred temperature & humidity',
    },
    {
      name: 'Routine Model',
      icon: Activity,
      color: 'grape',
      updates: mlStats?.routine_model_updates || 0,
      confidence: calculateConfidence(mlStats?.routine_model_updates || 0),
      description: 'Identifies daily patterns & habits',
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

  const overallConfidence = calculateConfidence(mlStats?.total_model_updates || 0, 5000);

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
                <Box>
                  <Text size="xs" c="rgba(255,255,255,0.8)">
                    Erratic Devices
                  </Text>
                  <Badge size="lg" color="red" variant="filled">
                    {mlStats.erratic_device_count}
                  </Badge>
                </Box>
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
          {overallConfidence < 25 && (
            <Text size="sm" c="dimmed">
              🌱 Early learning phase - AI is gathering baseline data from your home
            </Text>
          )}
          {overallConfidence >= 25 && overallConfidence < 50 && (
            <Text size="sm" c="dimmed">
              📊 Pattern recognition phase - AI is identifying routines and preferences
            </Text>
          )}
          {overallConfidence >= 50 && overallConfidence < 75 && (
            <Text size="sm" c="dimmed">
              🎯 Optimization phase - AI is refining predictions and improving accuracy
            </Text>
          )}
          {overallConfidence >= 75 && (
            <Text size="sm" c="dimmed">
              ✨ Mature learning - AI has strong confidence in predictions and routines
            </Text>
          )}

          {(mlStats?.erratic_device_count || 0) > 0 && (
            <Text size="sm" c="orange">
              ⚠️ {mlStats?.erratic_device_count} device{(mlStats?.erratic_device_count || 0) > 1 ? 's' : ''} showing
              erratic behavior - check for issues
            </Text>
          )}

          <Text size="sm" c="dimmed">
            💡 More data = better predictions. Keep your system running to improve AI accuracy.
          </Text>
        </Stack>
      </Paper>
    </Stack>
  );
}
