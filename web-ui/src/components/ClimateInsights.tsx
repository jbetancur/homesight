import { useState, useEffect } from 'react';
import { Paper, Text, Stack, ThemeIcon, Alert, Loader, Group, Badge, Divider, Accordion } from '@mantine/core';
import {
  Thermometer,
  AlertTriangle,
  CheckCircle2,
  Info,
  TrendingUp,
  Clock,
  Activity,
} from 'lucide-react';
import { API_BASE_WITH_PATHS } from '../apiConfig';

interface ClimateInsight {
  type: 'info' | 'warning' | 'success';
  title: string;
  description: string;
}

interface TrendPattern {
  device_id: string;
  device_name: string;
  zone_name: string | null;
  metric: string;
  pattern_type: string;
  daily_swing: number;
  min_value: number;
  max_value: number;
  typical_low_time: string | null;
  typical_high_time: string | null;
  insight: string;
  is_normal: boolean;
  likely_cause: string | null;
  recommendation: string | null;
}

interface ClimateInsightsResponse {
  insights: ClimateInsight[];
  trend_patterns?: TrendPattern[];
  timestamp: string;
  source: 'llm' | 'fallback' | 'error';
}

export default function ClimateInsights() {
  const [insights, setInsights] = useState<ClimateInsight[]>([]);
  const [trendPatterns, setTrendPatterns] = useState<TrendPattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchInsights = async () => {
      try {
        setLoading(true);

        const response = await fetch(`${API_BASE_WITH_PATHS}/hsil/climate-insights`);

        if (!response.ok) {
          throw new Error(`Failed to fetch insights: ${response.statusText}`);
        }

        const data: ClimateInsightsResponse = await response.json();
        setInsights(data.insights);
        setTrendPatterns(data.trend_patterns || []);
      } catch (err) {
        console.error('Error fetching climate insights:', err);
        // Set fallback insight
        setInsights([{
          type: 'warning',
          title: 'Insights Unavailable',
          description: 'Unable to load climate insights. Please check if the AI service is running.'
        }]);
        setTrendPatterns([]);
      } finally {
        setLoading(false);
      }
    };

    fetchInsights();
    // Refresh insights every 5 minutes
    const interval = setInterval(fetchInsights, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const getIcon = (type: string) => {
    switch (type) {
      case 'warning':
        return AlertTriangle;
      case 'success':
        return CheckCircle2;
      case 'info':
      default:
        return Info;
    }
  };

  const getColor = (type: string) => {
    switch (type) {
      case 'warning':
        return 'orange';
      case 'success':
        return 'green';
      case 'info':
      default:
        return 'blue';
    }
  };

  if (loading) {
    return (
      <Paper p="xl" withBorder>
        <Stack gap="md" align="center">
          <Loader size="lg" />
          <Text size="sm" c="dimmed">
            Analyzing climate conditions...
          </Text>
        </Stack>
      </Paper>
    );
  }

  if (insights.length === 0) {
    return (
      <Paper p="xl" withBorder>
        <Stack gap="md" align="center">
          <ThemeIcon size="xl" variant="light" color="gray" radius="xl">
            <Thermometer size={32} />
          </ThemeIcon>
          <Stack gap="xs" align="center">
            <Text size="lg" fw={600} ta="center">
              No Climate Data Available
            </Text>
            <Text size="sm" c="dimmed" ta="center" maw={500}>
              Climate insights require temperature or humidity sensors. Add compatible sensors to see AI-powered climate analysis.
            </Text>
          </Stack>
        </Stack>
      </Paper>
    );
  }

  const formatPatternType = (type: string) => {
    switch (type) {
      case 'morning_low_evening_high':
        return 'Morning Low → Evening High';
      case 'morning_high_evening_low':
        return 'Morning High → Evening Low';
      case 'diurnal_cycle':
        return 'Daily Cycle';
      default:
        return type.replace(/_/g, ' ');
    }
  };

  return (
    <Stack gap="md">
      {/* Current Insights */}
      {insights.map((insight, idx) => {
        const Icon = getIcon(insight.type);
        const color = getColor(insight.type);

        return (
          <Alert
            key={idx}
            icon={<Icon size={20} />}
            color={color}
            variant="light"
            title={insight.title}
          >
            <Text size="sm">{insight.description}</Text>
          </Alert>
        );
      })}

      {/* Trend Patterns Section */}
      {trendPatterns.length > 0 && (
        <>
          <Divider my="sm" label={
            <Group gap="xs">
              <TrendingUp size={16} />
              <Text size="sm" fw={500}>Temperature Trend Patterns</Text>
            </Group>
          } labelPosition="left" />

          <Accordion variant="contained" radius="md">
            {trendPatterns.map((pattern, idx) => (
              <Accordion.Item key={idx} value={`pattern-${idx}`}>
                <Accordion.Control>
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="sm">
                      <ThemeIcon
                        size="sm"
                        variant="light"
                        color={pattern.is_normal ? 'blue' : 'orange'}
                        radius="xl"
                      >
                        <Activity size={14} />
                      </ThemeIcon>
                      <div>
                        <Text size="sm" fw={500}>
                          {pattern.zone_name || pattern.device_name}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {pattern.metric === 'temperature' ? 'Temperature' : 'Humidity'} Pattern
                        </Text>
                      </div>
                    </Group>
                    <Group gap="xs">
                      <Badge
                        size="sm"
                        variant="light"
                        color={pattern.daily_swing > 6 ? 'orange' : 'blue'}
                      >
                        {pattern.daily_swing.toFixed(1)}°F swing
                      </Badge>
                      <Badge size="sm" variant="outline" color="gray">
                        {formatPatternType(pattern.pattern_type)}
                      </Badge>
                    </Group>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="sm">
                    {/* Pattern Details */}
                    <Group gap="xl">
                      <Group gap="xs">
                        <Clock size={14} />
                        <Text size="sm">
                          Low: <strong>{pattern.min_value.toFixed(1)}°F</strong>
                          {pattern.typical_low_time && ` (${pattern.typical_low_time})`}
                        </Text>
                      </Group>
                      <Group gap="xs">
                        <Clock size={14} />
                        <Text size="sm">
                          High: <strong>{pattern.max_value.toFixed(1)}°F</strong>
                          {pattern.typical_high_time && ` (${pattern.typical_high_time})`}
                        </Text>
                      </Group>
                    </Group>

                    {/* AI Insight */}
                    <Paper p="sm" withBorder bg="gray.0">
                      <Text size="sm">{pattern.insight}</Text>
                    </Paper>

                    {/* Likely Cause & Recommendation */}
                    {(pattern.likely_cause || pattern.recommendation) && (
                      <Group gap="md">
                        {pattern.likely_cause && (
                          <Badge size="sm" variant="dot" color="blue">
                            Cause: {pattern.likely_cause}
                          </Badge>
                        )}
                        {pattern.recommendation && (
                          <Badge size="sm" variant="dot" color="green">
                            {pattern.recommendation}
                          </Badge>
                        )}
                      </Group>
                    )}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </>
      )}
    </Stack>
  );
}
