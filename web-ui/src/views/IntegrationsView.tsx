
import { useNavigate } from 'react-router-dom';
import { Stack, Title, Text, Card, Grid, Group, Badge, Button, Paper } from '@mantine/core';
import { Radio, Wifi, Cloud, Plus, Settings, Activity } from 'lucide-react';

export function IntegrationsView() {
  const navigate = useNavigate();

  const integrations = [
    {
      id: 'zwave',
      name: 'Z-Wave',
      description: 'Z-Wave devices via Z-Wave JS',
      icon: Radio,
      color: '#228be6',
      path: '/integrations/zwave',
      implemented: true,
      actions: ['Start Inclusion', 'Start Exclusion', 'Heal Network', 'Re-Interview Node']
    },
    {
      id: 'zigbee',
      name: 'Zigbee2MQTT',
      description: 'Zigbee devices via MQTT',
      icon: Wifi,
      color: '#40c057',
      path: '/integrations/zigbee',
      implemented: false,
      actions: ['Permit Join', 'View Coordinator Info', 'Manage Bindings']
    },
    {
      id: 'lan',
      name: 'LAN Devices',
      description: 'Network-connected devices (Shelly, Tasmota)',
      icon: Wifi,
      color: '#f59f00',
      path: '/integrations/lan',
      implemented: false,
      actions: ['Scan Network', 'Manual Add', 'Configure Device']
    },
    {
      id: 'cloud',
      name: 'Cloud Integrations',
      description: 'Cloud-connected devices and services',
      icon: Cloud,
      color: '#9c36b5',
      path: '/integrations/cloud',
      implemented: false,
      actions: ['OAuth Connect', 'Manage Tokens', 'View Connected Devices']
    }
  ];

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Integrations</Title>
          <Text size="sm" c="dimmed">
            Connect and manage your home automation integrations
          </Text>
        </div>
      </Group>

      <Paper p="md" withBorder style={{ backgroundColor: '#f8f9fa' }}>
        <Stack gap="xs">
          <Group gap="xs">
            <Activity size={20} color="#228be6" />
            <Text size="sm" fw={600}>MQTT-Based Architecture</Text>
          </Group>
          <Text size="sm" c="dimmed">
            All integrations communicate via MQTT message bus for real-time device discovery and state updates.
            No synchronous discovery endpoints - devices appear automatically when published to MQTT.
          </Text>
        </Stack>
      </Paper>

      <Grid>
        {integrations.map((integration) => {
          const Icon = integration.icon;
          return (
            <Grid.Col key={integration.id} span={{ base: 12, sm: 6, md: 4 }}>
              <Card
                withBorder
                p="lg"
                style={{
                  height: '100%',
                  cursor: integration.implemented ? 'pointer' : 'default',
                  opacity: integration.implemented ? 1 : 0.6
                }}
                onClick={() => integration.implemented && navigate(integration.path)}
              >
                <Stack gap="md">
                  <Group justify="space-between" align="flex-start">
                    <Icon size={40} color={integration.color} />
                    {!integration.implemented && (
                      <Badge variant="light" color="gray" size="sm">
                        Coming Soon
                      </Badge>
                    )}
                  </Group>

                  <div>
                    <Text size="lg" fw={600}>{integration.name}</Text>
                    <Text size="sm" c="dimmed" mt={4}>
                      {integration.description}
                    </Text>
                  </div>

                  <Stack gap="xs">
                    <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                      Available Actions
                    </Text>
                    {integration.actions.map((action, idx) => (
                      <Group key={idx} gap={6}>
                        <div
                          style={{
                            width: 4,
                            height: 4,
                            borderRadius: '50%',
                            backgroundColor: integration.color
                          }}
                        />
                        <Text size="xs" c="dimmed">{action}</Text>
                      </Group>
                    ))}
                  </Stack>

                  {integration.implemented ? (
                    <Button
                      fullWidth
                      variant="light"
                      color={integration.color}
                      leftSection={<Settings size={16} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(integration.path);
                      }}
                    >
                      Manage Integration
                    </Button>
                  ) : (
                    <Button
                      fullWidth
                      variant="light"
                      color="gray"
                      disabled
                    >
                      Not Available
                    </Button>
                  )}
                </Stack>
              </Card>
            </Grid.Col>
          );
        })}
      </Grid>

      <Card withBorder p="md">
        <Stack gap="md">
          <Group gap="xs">
            <Plus size={20} color="#228be6" />
            <Text size="sm" fw={600}>Custom Integrations</Text>
          </Group>
          <Text size="sm" c="dimmed">
            Want to add your own integration? HomeSight uses MQTT for all device communication, making it easy
            to integrate custom devices in any programming language.
          </Text>
          <Group gap="md">
            <Button
              variant="light"
              size="sm"
              component="a"
              href="https://github.com/jbetancur/homesight/blob/main/docs/INTEGRATIONS_MQTT.md"
              target="_blank"
            >
              View MQTT Documentation
            </Button>
            <Button
              variant="light"
              size="sm"
              component="a"
              href="https://github.com/jbetancur/homesight"
              target="_blank"
            >
              GitHub Repository
            </Button>
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}
