import { useState, useEffect } from 'react';
import { Paper, Text, Stack, ThemeIcon, Alert, Loader } from '@mantine/core';
import {
  Thermometer,
  AlertTriangle,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { API_BASE_WITH_PATHS } from '../apiConfig';

interface ClimateInsight {
  type: 'info' | 'warning' | 'success';
  title: string;
  description: string;
}

interface ClimateInsightsResponse {
  insights: ClimateInsight[];
  timestamp: string;
  source: 'llm' | 'fallback' | 'error';
}

export default function ClimateInsights() {
  const [insights, setInsights] = useState<ClimateInsight[]>([]);
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
      } catch (err) {
        console.error('Error fetching climate insights:', err);
        // Set fallback insight
        setInsights([{
          type: 'warning',
          title: 'Insights Unavailable',
          description: 'Unable to load climate insights. Please check if the AI service is running.'
        }]);
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

  return (
    <Stack gap="md">
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
    </Stack>
  );
}
