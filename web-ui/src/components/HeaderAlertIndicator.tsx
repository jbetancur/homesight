import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ActionIcon,
  Indicator,
  Popover,
  Stack,
  Group,
  Text,
  Badge,
  Button,
  ScrollArea,
  Divider,
} from '@mantine/core';
import { Bell, AlertTriangle, CheckCircle, X, ChevronRight } from 'lucide-react';
import { useAlerts } from '../context/AlertsContext';
import type { Incident } from '../context/AlertsContext';

function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'red';
    case 'high':
      return 'orange';
    case 'medium':
      return 'yellow';
    default:
      return 'blue';
  }
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

interface AlertItemProps {
  incident: Incident;
  onAcknowledge: () => void;
  onDismiss: () => void;
  onViewDetails: () => void;
}

function AlertItem({ incident, onAcknowledge, onDismiss, onViewDetails }: AlertItemProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleAcknowledge = async () => {
    setActionLoading('ack');
    await onAcknowledge();
    setActionLoading(null);
  };

  const handleDismiss = async () => {
    setActionLoading('dismiss');
    await onDismiss();
    setActionLoading(null);
  };

  return (
    <Stack gap="xs" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-gray-0)' }}>
      <Group justify="space-between" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <AlertTriangle size={14} color={`var(--mantine-color-${getSeverityColor(incident.severity)}-6)`} />
          <Text size="sm" fw={500} lineClamp={1}>
            {incident.title}
          </Text>
        </Group>
        <Badge size="xs" color={getSeverityColor(incident.severity)} variant="light">
          {incident.severity}
        </Badge>
      </Group>

      <Text size="xs" c="dimmed" lineClamp={2}>
        {incident.description}
      </Text>

      <Group justify="space-between" wrap="nowrap">
        <Text size="xs" c="dimmed">
          {formatTimeAgo(incident.created_at)}
        </Text>
        <Group gap="xs">
          {incident.status === 'open' && (
            <Button
              size="compact-xs"
              variant="light"
              color="blue"
              leftSection={<CheckCircle size={12} />}
              loading={actionLoading === 'ack'}
              onClick={handleAcknowledge}
            >
              Ack
            </Button>
          )}
          <Button
            size="compact-xs"
            variant="light"
            color="gray"
            leftSection={<X size={12} />}
            loading={actionLoading === 'dismiss'}
            onClick={handleDismiss}
          >
            Dismiss
          </Button>
          <ActionIcon size="xs" variant="subtle" onClick={onViewDetails}>
            <ChevronRight size={14} />
          </ActionIcon>
        </Group>
      </Group>
    </Stack>
  );
}

export function HeaderAlertIndicator() {
  const [opened, setOpened] = useState(false);
  const navigate = useNavigate();
  const { activeIncidents, criticalCount, acknowledgeIncident, dismissIncident } = useAlerts();

  const totalCount = activeIncidents.length;
  const hasCritical = criticalCount > 0;

  const handleViewDetails = (incident: Incident) => {
    setOpened(false);
    navigate('/incidents', { state: { highlightId: incident.id } });
  };

  const handleViewAll = () => {
    setOpened(false);
    navigate('/incidents');
  };

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      width={360}
      shadow="md"
      withArrow
    >
      <Popover.Target>
        <Indicator
          disabled={totalCount === 0}
          color={hasCritical ? 'red' : 'orange'}
          size={18}
          label={totalCount > 0 ? totalCount : undefined}
          offset={4}
        >
          <ActionIcon
            variant={totalCount > 0 ? 'light' : 'subtle'}
            color={hasCritical ? 'red' : totalCount > 0 ? 'orange' : 'gray'}
            size="lg"
            onClick={() => setOpened(o => !o)}
          >
            <Bell size={20} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>

      <Popover.Dropdown p={0}>
        <Stack gap={0}>
          <Group justify="space-between" p="sm" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)' }}>
            <Text fw={600} size="sm">
              Active Alerts
            </Text>
            <Badge size="sm" color={hasCritical ? 'red' : 'orange'}>
              {totalCount}
            </Badge>
          </Group>

          {totalCount === 0 ? (
            <Stack align="center" p="lg" gap="xs">
              <CheckCircle size={32} color="var(--mantine-color-green-6)" />
              <Text size="sm" c="dimmed">
                No active alerts
              </Text>
            </Stack>
          ) : (
            <>
              <ScrollArea.Autosize mah={300}>
                <Stack gap="xs" p="xs">
                  {activeIncidents.slice(0, 5).map(incident => (
                    <AlertItem
                      key={incident.id}
                      incident={incident}
                      onAcknowledge={() => acknowledgeIncident(incident.id)}
                      onDismiss={() => dismissIncident(incident.id)}
                      onViewDetails={() => handleViewDetails(incident)}
                    />
                  ))}
                </Stack>
              </ScrollArea.Autosize>

              {totalCount > 5 && (
                <>
                  <Divider />
                  <Text size="xs" c="dimmed" ta="center" py="xs">
                    +{totalCount - 5} more alerts
                  </Text>
                </>
              )}

              <Divider />
              <Button
                variant="subtle"
                fullWidth
                size="sm"
                onClick={handleViewAll}
                rightSection={<ChevronRight size={14} />}
              >
                View All Incidents
              </Button>
            </>
          )}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
