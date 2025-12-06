export interface DeviceReadings {
  // Temperature sensors
  'Air temperature'?: number;
  temperature?: number;
  // Humidity sensors
  Humidity?: number;
  humidity?: number;
  // Water leak sensors
  'Water Alarm'?: number;
  water?: number;
  // Generic alarm values
  alarmLevel?: number;
  alarmType?: number;
  // Allow other readings
  [key: string]: number | undefined;
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
  battery_level?: number;
  metadata?: Record<string, any>;
  readings?: DeviceReadings;
}

export interface ZoneAttributes {
  floor_type?: string;
  square_feet?: number;
  has_windows?: boolean;
  has_fireplace?: boolean;
  has_hvac_return?: boolean;
  has_hvac_vent?: boolean;
  has_radiant_heat?: boolean;
  has_ceiling_fan?: boolean;
  has_plumbing?: boolean;
  has_water_heater?: boolean;
  has_washer?: boolean;
  has_sump_pump?: boolean;
  has_valuables?: boolean;
  has_pets?: boolean;
  has_infant?: boolean;
  has_elderly?: boolean;
  is_occupied_daily?: boolean;
  tags?: string[];
  [key: string]: string | number | boolean | string[] | undefined;
}

export interface Room {
  id: string;
  name: string;
  type: string;
  devices: Device[];
  attributes?: ZoneAttributes;
}
