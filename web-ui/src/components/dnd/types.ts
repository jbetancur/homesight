export interface DeviceReadings {
  // Temperature sensors (standardized to Fahrenheit)
  temperature_f?: number;
  // Humidity sensors
  Humidity?: number;
  humidity?: number;
  // Binary sensors
  water?: boolean | number;
  motion?: boolean;
  contact?: boolean;
  tamper?: boolean;
  smoke?: boolean;
  co?: boolean;
  // Power/Energy
  power_w?: number;
  energy_kwh?: number;
  voltage_v?: number;
  current_a?: number;
  // Other sensors
  illuminance?: number;
  co2?: number;
  voc?: number;
  pm25?: number;
  pressure?: number;
  uv_index?: number;
  // Legacy/backward compatibility
  'Water Alarm'?: number;
  alarmLevel?: number;
  alarmType?: number;
  // Allow other readings
  [key: string]: number | boolean | undefined;
}

export interface DeviceBattery {
  level: number;
  is_low: boolean;
  is_charging: boolean;
}

export interface DeviceConnectivity {
  online: boolean;
  signal_strength?: number;
  last_seen: string;
  firmware_version?: string;
}

export interface DeviceControls {
  switch?: { value: boolean; settable: boolean };
  level?: { value: number; settable: boolean; min: number; max: number };
  color?: { r: number; g: number; b: number; settable: boolean };
  thermostat?: { mode: string; setpoint_heat?: number; setpoint_cool?: number; settable: boolean };
  lock?: { locked: boolean; settable: boolean };
}

export type EntityType = 'sensor' | 'binary_sensor' | 'switch' | 'number' | 'alarm' | 'diagnostic' | 'config';

export interface DeviceEntity {
  id: string;
  device_id: string;
  entity_type: EntityType;
  name: string;
  category: string;
  value: any;
  unit: string;
  settable: boolean;
  metadata: Record<string, any>;
  updated_at: string;
}

export interface Device {
  id: string;
  name: string;
  alias?: string;
  type: string;
  value: number | boolean | null;
  state: 'normal' | 'warning' | 'critical' | 'unknown';
  location?: string;
  zone_id?: string;
  unit?: string;
  active: boolean;
  last_updated?: string;
  trend?: 'up' | 'down' | 'stable';

  // Unified contract
  readings?: DeviceReadings;
  controls?: DeviceControls;
  battery?: DeviceBattery;
  connectivity?: DeviceConnectivity;
  raw_data?: Record<string, any>;

  // Entity-Based Model (New - more flexible)
  entities?: DeviceEntity[];

  // Backward compatibility (API still includes these)
  battery_level?: number;
  metadata?: Record<string, any>;
}

export interface ZoneAttributes {
  // All attributes are dynamic and loaded from the backend schema
  // This interface only provides type safety for the map structure
  [key: string]: string | number | boolean | string[] | undefined;
}

export interface Room {
  id: string;
  name: string;
  type: string;
  devices: Device[];
  attributes?: ZoneAttributes;
}
