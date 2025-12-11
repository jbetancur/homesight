
import { useState } from 'react';
import { Card, Group, Stack, Text, Switch, Slider, Badge, Button, Paper } from '@mantine/core';
import {
  Power, Sun, Droplets, Thermometer, DoorClosed, Lock, Unlock, Battery,
  Signal, Activity, Zap, Gauge, AlertTriangle, CheckCircle
} from 'lucide-react';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;

interface WidgetProps {
  deviceId: string;
  capability: string;
  state?: any;
  metadata?: any;
  onCommand?: (command: string, args: any) => Promise<void>;
}

// Helper function to send commands
async function sendDeviceCommand(deviceId: string, command: string, args: any = {}) {
  try {
    const response = await fetch(`${API_BASE}/devices/${deviceId}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, args }),
    });

    if (!response.ok) {
      throw new Error('Command failed');
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to send command:', error);
    throw error;
  }
}

// OnOff Widget
export function OnOffWidget({ deviceId, state, onCommand }: WidgetProps) {
  // Check multiple sources for the switch state
  const initialState = state?.on || state?.currentValue || state?.targetValue || false;
  const [isOn, setIsOn] = useState(initialState);
  const [loading, setLoading] = useState(false);

  const handleToggle = async (value: boolean) => {
    setLoading(true);
    try {
      if (onCommand) {
        await onCommand('set_switch', { on: value });
      } else {
        await sendDeviceCommand(deviceId, 'set_switch', { on: value });
      }
      setIsOn(value);
    } catch (error) {
      console.error('Failed to toggle:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <Power size={24} color={isOn ? '#40c057' : '#868e96'} />
          <div>
            <Text fw={600}>Power</Text>
            <Text size="xs" c="dimmed">{isOn ? 'On' : 'Off'}</Text>
          </div>
        </Group>
        <Switch
          size="lg"
          checked={isOn}
          onChange={(e) => handleToggle(e.currentTarget.checked)}
          disabled={loading}
        />
      </Group>
    </Card>
  );
}

// Brightness Widget
export function BrightnessWidget({ deviceId, state, onCommand }: WidgetProps) {
  const [brightness, setBrightness] = useState(state?.brightness || 0);
  const [loading, setLoading] = useState(false);

  const handleChange = async (value: number) => {
    setBrightness(value);
    setLoading(true);
    try {
      if (onCommand) {
        await onCommand('set_brightness', { brightness: value });
      } else {
        await sendDeviceCommand(deviceId, 'set_brightness', { brightness: value });
      }
    } catch (error) {
      console.error('Failed to set brightness:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card withBorder p="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="sm">
            <Sun size={24} color="#fab005" />
            <div>
              <Text fw={600}>Brightness</Text>
              <Text size="xs" c="dimmed">{brightness}%</Text>
            </div>
          </Group>
        </Group>
        <Slider
          value={brightness}
          onChange={handleChange}
          min={0}
          max={100}
          disabled={loading}
          marks={[
            { value: 0, label: '0%' },
            { value: 50, label: '50%' },
            { value: 100, label: '100%' },
          ]}
        />
      </Stack>
    </Card>
  );
}

// Temperature Widget (Read-only)
export function TemperatureWidget({ state }: WidgetProps) {
  const tempF = state?.temperature_f || 0;

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <Thermometer size={24} color="#228be6" />
          <div>
            <Text fw={600}>Temperature</Text>
            <Text size="xs" c="dimmed">
              {tempF.toFixed(1)}°F
            </Text>
          </div>
        </Group>
        <Text size="xl" fw={700}>{tempF.toFixed(1)}°F</Text>
      </Group>
    </Card>
  );
}

// Humidity Widget (Read-only)
export function HumidityWidget({ state }: WidgetProps) {
  const humidity = state?.humidity || state?.humidity_percent || 0;

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <Droplets size={24} color="#4dabf7" />
          <div>
            <Text fw={600}>Humidity</Text>
            <Text size="xs" c="dimmed">Relative humidity</Text>
          </div>
        </Group>
        <Text size="xl" fw={700}>{humidity}%</Text>
      </Group>
    </Card>
  );
}

// Lock Widget
export function LockWidget({ deviceId, state, onCommand }: WidgetProps) {
  const [locked, setLocked] = useState(state?.locked !== false);
  const [loading, setLoading] = useState(false);

  const handleToggle = async () => {
    setLoading(true);
    try {
      const newState = !locked;
      if (onCommand) {
        await onCommand(newState ? 'lock' : 'unlock', {});
      } else {
        await sendDeviceCommand(deviceId, newState ? 'lock' : 'unlock', {});
      }
      setLocked(newState);
    } catch (error) {
      console.error('Failed to toggle lock:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          {locked ? <Lock size={24} color="#fa5252" /> : <Unlock size={24} color="#40c057" />}
          <div>
            <Text fw={600}>Lock</Text>
            <Text size="xs" c="dimmed">{locked ? 'Locked' : 'Unlocked'}</Text>
          </div>
        </Group>
        <Button
          color={locked ? 'green' : 'red'}
          onClick={handleToggle}
          disabled={loading}
          loading={loading}
        >
          {locked ? 'Unlock' : 'Lock'}
        </Button>
      </Group>
    </Card>
  );
}

// Contact Sensor Widget (Read-only)
export function ContactWidget({ state }: WidgetProps) {
  const isOpen = state?.open || state?.contact_open || false;

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <DoorClosed size={24} color={isOpen ? '#fa5252' : '#40c057'} />
          <div>
            <Text fw={600}>Contact Sensor</Text>
            <Text size="xs" c="dimmed">{isOpen ? 'Open' : 'Closed'}</Text>
          </div>
        </Group>
        <Badge color={isOpen ? 'red' : 'green'} size="lg">
          {isOpen ? 'Open' : 'Closed'}
        </Badge>
      </Group>
    </Card>
  );
}

// Motion Sensor Widget (Read-only)
export function MotionWidget({ state }: WidgetProps) {
  const motion = state?.motion || false;
  const lastMotion = state?.last_motion ? new Date(state.last_motion) : null;

  return (
    <Card withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="sm">
            <Activity size={24} color={motion ? '#fab005' : '#868e96'} />
            <div>
              <Text fw={600}>Motion</Text>
              <Text size="xs" c="dimmed">{motion ? 'Detected' : 'Clear'}</Text>
            </div>
          </Group>
          <Badge color={motion ? 'orange' : 'gray'} size="lg">
            {motion ? 'Motion' : 'No Motion'}
          </Badge>
        </Group>
        {lastMotion && (
          <Text size="xs" c="dimmed">
            Last detected: {lastMotion.toLocaleString()}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

// Battery Widget (Read-only)
export function BatteryWidget({ state }: WidgetProps) {
  const level = state?.battery || state?.battery_level || 100;
  const charging = state?.charging || false;

  const getColor = () => {
    if (level > 50) return 'green';
    if (level > 20) return 'yellow';
    return 'red';
  };

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <Battery size={24} color={level > 20 ? '#40c057' : '#fa5252'} />
          <div>
            <Text fw={600}>Battery</Text>
            <Text size="xs" c="dimmed">{charging ? 'Charging' : 'Discharging'}</Text>
          </div>
        </Group>
        <Badge color={getColor()} size="lg">
          {level}%
        </Badge>
      </Group>
    </Card>
  );
}

// Signal Strength Widget (Read-only)
export function SignalWidget({ state, metadata }: WidgetProps) {
  const rssi = state?.rssi || metadata?.rssi || 0;
  const lqi = state?.lqi || metadata?.lqi || 0;

  const getSignalStrength = () => {
    if (rssi > -60) return { label: 'Excellent', color: 'green' };
    if (rssi > -70) return { label: 'Good', color: 'blue' };
    if (rssi > -80) return { label: 'Fair', color: 'yellow' };
    return { label: 'Weak', color: 'red' };
  };

  const strength = getSignalStrength();

  return (
    <Card withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="sm">
            <Signal size={24} color="#228be6" />
            <div>
              <Text fw={600}>Signal Strength</Text>
              <Text size="xs" c="dimmed">{strength.label}</Text>
            </div>
          </Group>
          <Badge color={strength.color} size="lg">
            {rssi} dBm
          </Badge>
        </Group>
        {lqi > 0 && (
          <Text size="xs" c="dimmed">
            Link Quality: {lqi}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

// Energy/Power Widget (Read-only)
export function EnergyWidget({ state }: WidgetProps) {
  const power = state?.power || state?.power_w || 0;
  const energy = state?.energy || state?.energy_kwh || 0;

  return (
    <Card withBorder p="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="sm">
            <Zap size={24} color="#fab005" />
            <div>
              <Text fw={600}>Power Usage</Text>
              <Text size="xs" c="dimmed">Current consumption</Text>
            </div>
          </Group>
          <Text size="xl" fw={700}>{power.toFixed(1)} W</Text>
        </Group>
        {energy > 0 && (
          <Paper p="xs" withBorder bg="gray.0">
            <Text size="xs" c="dimmed">
              Total Energy: {energy.toFixed(2)} kWh
            </Text>
          </Paper>
        )}
      </Stack>
    </Card>
  );
}

// Valve Status Widget (Read-only - shows jammed/operational status)
export function ValveStatusWidget({ state }: WidgetProps) {
  // Z-Wave Notification CC 113 for Water Valve
  // water=7 typically means "Valve operation jammed"
  // water=0 means no alarm/operational
  const valveStatus = state?.water || 0;
  const isJammed = valveStatus === 7;
  const alarmLevel = state?.alarmLevel || 0;

  const getStatusInfo = () => {
    if (isJammed) {
      return {
        label: 'Jammed',
        message: 'Valve operation jammed - check for obstruction',
        color: 'red',
        icon: <AlertTriangle size={24} color="#fa5252" />
      };
    }
    return {
      label: 'Operational',
      message: 'Valve operating normally',
      color: 'green',
      icon: <CheckCircle size={24} color="#40c057" />
    };
  };

  const status = getStatusInfo();

  return (
    <Card withBorder p="md" bg={isJammed ? 'red.0' : undefined}>
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="sm">
            {status.icon}
            <div>
              <Text fw={600}>Valve Status</Text>
              <Text size="xs" c="dimmed">{status.message}</Text>
            </div>
          </Group>
          <Badge color={status.color} size="lg">
            {status.label}
          </Badge>
        </Group>
        {isJammed && (
          <Paper p="xs" withBorder bg="red.1">
            <Text size="xs" c="red.9" fw={600}>
              ⚠️ Action Required: Check valve for physical obstruction or manual override
            </Text>
          </Paper>
        )}
        {alarmLevel > 0 && (
          <Text size="xs" c="dimmed">
            Alarm Level: {alarmLevel}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

// Generic Sensor Widget (Read-only for unknown capabilities)
export function GenericSensorWidget({ capability, state }: WidgetProps) {
  const value = state?.[capability] || state?.value || '-';

  return (
    <Card withBorder p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <Gauge size={24} color="#868e96" />
          <div>
            <Text fw={600} tt="capitalize">{capability.replace(/_/g, ' ')}</Text>
            <Text size="xs" c="dimmed">Sensor value</Text>
          </div>
        </Group>
        <Text size="xl" fw={700}>{value}</Text>
      </Group>
    </Card>
  );
}

// Widget Selector - Returns the appropriate widget based on capability
export function CapabilityWidget(props: WidgetProps) {
  const { capability } = props;

  switch (capability.toLowerCase()) {
    case 'onoff':
    case 'switch':
      return <OnOffWidget {...props} />;
    case 'brightness':
    case 'level':
      return <BrightnessWidget {...props} />;
    case 'temperature':
      return <TemperatureWidget {...props} />;
    case 'humidity':
      return <HumidityWidget {...props} />;
    case 'lock':
      return <LockWidget {...props} />;
    case 'contact':
    case 'door':
      return <ContactWidget {...props} />;
    case 'motion':
      return <MotionWidget {...props} />;
    case 'battery':
      return <BatteryWidget {...props} />;
    case 'signal':
    case 'rssi':
      return <SignalWidget {...props} />;
    case 'energy':
    case 'power':
      return <EnergyWidget {...props} />;
    case 'valve_status':
    case 'valve':
      return <ValveStatusWidget {...props} />;
    default:
      return <GenericSensorWidget {...props} />;
  }
}
