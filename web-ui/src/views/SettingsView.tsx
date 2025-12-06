import { useState, useEffect } from 'react';
import {
  Container,
  Title,
  Tabs,
  Paper,
  TextInput,
  NumberInput,
  Select,
  Switch,
  Button,
  Group,
  Stack,
  Grid,
  Badge,
  Text,
  Accordion,
  LoadingOverlay,
  Alert,
  Modal,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { Home, DoorOpen, Database, Check, AlertCircle, Plus, Trash2, Edit2 } from 'lucide-react';
import { API_BASE } from '../apiConfig';

interface HomeProfile {
  id: string;
  home_id: string;
  year_built?: number;
  square_feet?: number;
  stories?: number;
  foundation_type?: string;
  roof_type?: string;
  roof_age?: number;
  siding_type?: string;
  window_type?: string;
  insulation?: string;
  hvac_type?: string;
  hvac_age?: number;
  has_ac?: boolean;
  ac_type?: string;
  heating_type?: string;
  thermostat_type?: string;
  has_humidifier?: boolean;
  has_dehumidifier?: boolean;
  has_air_purifier?: boolean;
  water_heater_type?: string;
  water_heater_age?: number;
  water_heater_fuel?: string;
  has_well_water?: boolean;
  has_sewer_system?: boolean;
  has_septic_system?: boolean;
  has_sump_pump?: boolean;
  electrical_panel?: string;
  has_generator_backup?: boolean;
  has_solar_panels?: boolean;
  has_battery_backup?: boolean;
  has_security_system?: boolean;
  has_fire_alarms?: boolean;
  has_co_alarms?: boolean;
  has_sprinklers?: boolean;
}

interface AttributeDefinition {
  id: string;
  name: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'select';
  scope: 'zone' | 'home';
  category: string;
  description: string;
  options?: string[];
  default_value?: string;
  required: boolean;
}

interface Zone {
  id: string;
  name: string;
  type: string;
}

interface ZoneTypeOption {
  value: string;
  label: string;
}

interface ZoneSchema {
  zone_types: ZoneTypeOption[];
}

export default function SettingsView() {
  const [activeTab, setActiveTab] = useState<string | null>('home');
  const [loading, setLoading] = useState(false);
  const [homeProfile, setHomeProfile] = useState<HomeProfile | null>(null);
  const [attributeDefs, setAttributeDefs] = useState<AttributeDefinition[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [zoneAttributes, setZoneAttributes] = useState<Record<string, Record<string, string>>>({});
  const [zoneSchema, setZoneSchema] = useState<ZoneSchema | null>(null);
  
  // Add zone modal state
  const [addZoneModalOpen, setAddZoneModalOpen] = useState(false);
  const [newZoneType, setNewZoneType] = useState<string>('');
  const [newZoneName, setNewZoneName] = useState<string>('');

  useEffect(() => {
    loadHomeProfile();
    loadAttributeDefinitions();
    loadZones();
    loadZoneSchema();
  }, []);

  const loadHomeProfile = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/home/profile`);
      const data = await response.json();
      setHomeProfile(data);
    } catch (error) {
      console.error('Failed to load home profile:', error);
    }
  };

  const loadAttributeDefinitions = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/zone-attributes/definitions?scope=zone`);
      const data = await response.json();
      setAttributeDefs(data || []);
    } catch (error) {
      console.error('Failed to load attribute definitions:', error);
    }
  };

  const loadZoneSchema = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/zones/schema`);
      const data = await response.json();
      setZoneSchema(data);
    } catch (error) {
      console.error('Failed to load zone schema:', error);
    }
  };

  const loadZones = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/zones`);
      const data = await response.json();
      setZones(data || []);
      
      // Load attributes for each zone
      const attrs: Record<string, Record<string, string>> = {};
      for (const zone of data || []) {
        try {
          const attrResponse = await fetch(`${API_BASE}/api/zones/${zone.id}/attributes`);
          const attrData = await attrResponse.json();
          attrs[zone.id] = attrData || {};
        } catch (error) {
          console.error(`Failed to load attributes for zone ${zone.id}:`, error);
          attrs[zone.id] = {};
        }
      }
      setZoneAttributes(attrs);
    } catch (error) {
      console.error('Failed to load zones:', error);
    }
  };

  const saveHomeProfile = async () => {
    if (!homeProfile) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/home/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(homeProfile),
      });
      
      if (response.ok) {
        notifications.show({
          title: 'Success',
          message: 'Home profile saved',
          color: 'green',
          icon: <Check size={18} />,
        });
      } else {
        throw new Error('Failed to save');
      }
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to save home profile',
        color: 'red',
        icon: <AlertCircle size={18} />,
      });
    } finally {
      setLoading(false);
    }
  };

  const saveZoneAttributes = async (zoneId: string) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/zones/${zoneId}/attributes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(zoneAttributes[zoneId] || {}),
      });
      
      if (response.ok) {
        notifications.show({
          title: 'Success',
          message: 'Zone attributes saved',
          color: 'green',
          icon: <Check size={18} />,
        });
      } else {
        throw new Error('Failed to save');
      }
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to save zone attributes',
        color: 'red',
        icon: <AlertCircle size={18} />,
      });
    } finally {
      setLoading(false);
    }
  };

  const updateZoneAttribute = (zoneId: string, attrId: string, value: string) => {
    setZoneAttributes(prev => ({
      ...prev,
      [zoneId]: {
        ...(prev[zoneId] || {}),
        [attrId]: value,
      },
    }));
  };

  const handleAddZone = async () => {
    if (!newZoneType || !newZoneName) return;
    
    const zoneId = newZoneName.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    
    try {
      const response = await fetch(`${API_BASE}/api/zones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: zoneId,
          name: newZoneName,
          type: newZoneType,
          home_id: 'default',
        }),
      });
      
      if (response.ok) {
        notifications.show({
          title: 'Success',
          message: 'Zone created successfully',
          color: 'green',
        });
        setAddZoneModalOpen(false);
        setNewZoneType('');
        setNewZoneName('');
        loadZones();
      }
    } catch {
      notifications.show({
        title: 'Error',
        message: 'Failed to create zone',
        color: 'red',
      });
    }
  };

  // Auto-fill zone name when type changes
  useEffect(() => {
    if (newZoneType && !newZoneName) {
      const typeName = newZoneType.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
      setNewZoneName(typeName);
    }
  }, [newZoneType, newZoneName]);

  const renderAttributeInput = (zoneId: string, def: AttributeDefinition) => {
    const value = zoneAttributes[zoneId]?.[def.id] || '';
    
    switch (def.type) {
      case 'boolean':
        return (
          <Switch
            label={def.label}
            description={def.description}
            checked={value === 'true'}
            onChange={(e) => updateZoneAttribute(zoneId, def.id, e.currentTarget.checked ? 'true' : 'false')}
          />
        );
      case 'number':
        return (
          <NumberInput
            label={def.label}
            description={def.description}
            value={value ? parseInt(value) : undefined}
            onChange={(val) => updateZoneAttribute(zoneId, def.id, val?.toString() || '')}
          />
        );
      case 'select':
        return (
          <Select
            label={def.label}
            description={def.description}
            data={def.options || []}
            value={value}
            onChange={(val) => updateZoneAttribute(zoneId, def.id, val || '')}
            clearable
          />
        );
      default:
        return (
          <TextInput
            label={def.label}
            description={def.description}
            value={value}
            onChange={(e) => updateZoneAttribute(zoneId, def.id, e.currentTarget.value)}
          />
        );
    }
  };

  const groupedAttributes = attributeDefs.reduce((acc, def) => {
    if (!acc[def.category]) acc[def.category] = [];
    acc[def.category].push(def);
    return acc;
  }, {} as Record<string, AttributeDefinition[]>);

  return (
    <Container size="lg" py="xl">
      <Title order={2} mb="lg">Settings</Title>
      
      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab value="home" leftSection={<Home size={16} />}>
            Home Profile
          </Tabs.Tab>
          <Tabs.Tab value="manage-zones" leftSection={<DoorOpen size={16} />}>
            Manage Zones
          </Tabs.Tab>
          <Tabs.Tab value="zones" leftSection={<DoorOpen size={16} />}>
            Zone Attributes
          </Tabs.Tab>
          <Tabs.Tab value="schema" leftSection={<Database size={16} />}>
            Attribute Schema
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="home" pt="lg">
          <Paper shadow="sm" p="xl" withBorder pos="relative">
            <LoadingOverlay visible={loading} />
            
            {!homeProfile ? (
              <Alert color="blue" icon={<AlertCircle size={18} />}>
                Loading home profile...
              </Alert>
            ) : (
              <Stack gap="lg">
                <Title order={3}>Construction Details</Title>
                <Grid>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="Year Built"
                      value={homeProfile.year_built}
                      onChange={(val) => setHomeProfile({ ...homeProfile, year_built: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="Square Feet"
                      value={homeProfile.square_feet}
                      onChange={(val) => setHomeProfile({ ...homeProfile, square_feet: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="Stories"
                      value={homeProfile.stories}
                      onChange={(val) => setHomeProfile({ ...homeProfile, stories: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Select
                      label="Foundation Type"
                      data={['slab', 'crawlspace', 'basement', 'pier']}
                      value={homeProfile.foundation_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, foundation_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Select
                      label="Roof Type"
                      data={['shingle', 'metal', 'tile', 'flat']}
                      value={homeProfile.roof_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, roof_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="Roof Age (years)"
                      value={homeProfile.roof_age}
                      onChange={(val) => setHomeProfile({ ...homeProfile, roof_age: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Select
                      label="Siding Type"
                      data={['vinyl', 'brick', 'wood', 'stucco', 'fiber-cement']}
                      value={homeProfile.siding_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, siding_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Select
                      label="Window Type"
                      data={['single-pane', 'double-pane', 'triple-pane']}
                      value={homeProfile.window_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, window_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                </Grid>

                <Title order={3} mt="xl">HVAC Systems</Title>
                <Grid>
                  <Grid.Col span={6}>
                    <Select
                      label="HVAC Type"
                      data={['central', 'mini-split', 'radiant', 'heat-pump', 'geothermal']}
                      value={homeProfile.hvac_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, hvac_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="HVAC Age (years)"
                      value={homeProfile.hvac_age}
                      onChange={(val) => setHomeProfile({ ...homeProfile, hvac_age: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Air Conditioning"
                      checked={homeProfile.has_ac}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_ac: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Select
                      label="Heating Type"
                      data={['gas', 'electric', 'oil', 'heat-pump', 'wood']}
                      value={homeProfile.heating_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, heating_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Humidifier"
                      checked={homeProfile.has_humidifier}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_humidifier: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Dehumidifier"
                      checked={homeProfile.has_dehumidifier}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_dehumidifier: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                </Grid>

                <Title order={3} mt="xl">Water & Plumbing</Title>
                <Grid>
                  <Grid.Col span={6}>
                    <Select
                      label="Water Heater Type"
                      data={['tank', 'tankless', 'heat-pump', 'solar']}
                      value={homeProfile.water_heater_type}
                      onChange={(val) => setHomeProfile({ ...homeProfile, water_heater_type: val || undefined })}
                      clearable
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <NumberInput
                      label="Water Heater Age (years)"
                      value={homeProfile.water_heater_age}
                      onChange={(val) => setHomeProfile({ ...homeProfile, water_heater_age: val as number })}
                    />
                  </Grid.Col>
                  <Grid.Col span={4}>
                    <Switch
                      label="Has Well Water"
                      checked={homeProfile.has_well_water}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_well_water: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={4}>
                    <Switch
                      label="Has Sewer System"
                      checked={homeProfile.has_sewer_system}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_sewer_system: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={4}>
                    <Switch
                      label="Has Sump Pump"
                      checked={homeProfile.has_sump_pump}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_sump_pump: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                </Grid>

                <Title order={3} mt="xl">Safety & Security</Title>
                <Grid>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Security System"
                      checked={homeProfile.has_security_system}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_security_system: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Fire Alarms"
                      checked={homeProfile.has_fire_alarms}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_fire_alarms: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has CO Alarms"
                      checked={homeProfile.has_co_alarms}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_co_alarms: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Switch
                      label="Has Solar Panels"
                      checked={homeProfile.has_solar_panels}
                      onChange={(e) => setHomeProfile({ ...homeProfile, has_solar_panels: e.currentTarget.checked })}
                    />
                  </Grid.Col>
                </Grid>

                <Group justify="flex-end" mt="xl">
                  <Button onClick={saveHomeProfile} loading={loading}>
                    Save Home Profile
                  </Button>
                </Group>
              </Stack>
            )}
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="manage-zones" pt="lg">
          <Paper shadow="sm" p="xl" withBorder>
            <Stack gap="lg">
              <Group justify="space-between">
                <Title order={3}>Manage Zones (Rooms)</Title>
                <Button
                  leftSection={<Plus size={16} />}
                  onClick={() => setAddZoneModalOpen(true)}
                >
                  Add Zone
                </Button>
              </Group>

              <Alert color="blue" icon={<AlertCircle size={18} />}>
                Zones represent physical rooms or areas in your home. Add zones here, then configure their attributes in the "Zone Attributes" tab.
              </Alert>

              <Stack gap="sm">
                {zones.map((zone) => (
                  <Paper key={zone.id} p="md" withBorder>
                    <Group justify="space-between">
                      <Stack gap={4}>
                        <Text fw={500}>{zone.name}</Text>
                        <Group gap="xs">
                          <Badge size="sm" variant="light">{zone.type}</Badge>
                          <Text size="sm" c="dimmed">ID: {zone.id}</Text>
                        </Group>
                      </Stack>
                      <Group gap="xs">
                        <Button
                          size="xs"
                          variant="light"
                          leftSection={<Edit2 size={14} />}
                          onClick={() => {
                            const newName = prompt('Enter new zone name:', zone.name);
                            if (!newName || newName === zone.name) return;
                            
                            fetch(`${API_BASE}/api/zones/${zone.id}`, {
                              method: 'PUT',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                ...zone,
                                name: newName,
                              }),
                            })
                              .then(() => {
                                notifications.show({
                                  title: 'Success',
                                  message: 'Zone updated successfully',
                                  color: 'green',
                                });
                                loadZones();
                              })
                              .catch(() => {
                                notifications.show({
                                  title: 'Error',
                                  message: 'Failed to update zone',
                                  color: 'red',
                                });
                              });
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="xs"
                          color="red"
                          variant="light"
                          leftSection={<Trash2 size={14} />}
                          onClick={() => {
                            if (!confirm(`Delete zone "${zone.name}"? Devices in this zone will need to be reassigned.`)) return;
                            
                            fetch(`${API_BASE}/api/zones/${zone.id}`, {
                              method: 'DELETE',
                            })
                              .then(() => {
                                notifications.show({
                                  title: 'Success',
                                  message: 'Zone deleted successfully',
                                  color: 'green',
                                });
                                loadZones();
                              })
                              .catch(() => {
                                notifications.show({
                                  title: 'Error',
                                  message: 'Failed to delete zone',
                                  color: 'red',
                                });
                              });
                          }}
                        >
                          Delete
                        </Button>
                      </Group>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="zones" pt="lg">
          <Stack gap="md">
            {zones.length === 0 ? (
              <Alert color="blue" icon={<AlertCircle size={18} />}>
                No zones configured yet.
              </Alert>
            ) : (
              <Accordion variant="separated">
                {zones.map((zone) => (
                  <Accordion.Item key={zone.id} value={zone.id}>
                    <Accordion.Control>
                      <Group justify="space-between">
                        <div>
                          <Text fw={500}>{zone.name}</Text>
                          <Text size="xs" c="dimmed">{zone.type}</Text>
                        </div>
                        <Group gap="xs">
                          {Object.keys(zoneAttributes[zone.id] || {}).length > 0 && (
                            <Badge size="sm" variant="light">
                              {Object.keys(zoneAttributes[zone.id] || {}).length} attributes
                            </Badge>
                          )}
                        </Group>
                      </Group>
                    </Accordion.Control>
                    <Accordion.Panel>
                      <Paper shadow="xs" p="md" withBorder pos="relative">
                        <LoadingOverlay visible={loading} />
                        <Stack gap="md">
                          {Object.entries(groupedAttributes).map(([category, defs]) => (
                            <div key={category}>
                              <Text fw={600} size="sm" mb="xs" c="dimmed">
                                {category}
                              </Text>
                              <Stack gap="sm">
                                {defs.map((def) => (
                                  <div key={def.id}>
                                    {renderAttributeInput(zone.id, def)}
                                  </div>
                                ))}
                              </Stack>
                            </div>
                          ))}
                          <Group justify="flex-end" mt="md">
                            <Button onClick={() => saveZoneAttributes(zone.id)} loading={loading}>
                              Save {zone.name} Attributes
                            </Button>
                          </Group>
                        </Stack>
                      </Paper>
                    </Accordion.Panel>
                  </Accordion.Item>
                ))}
              </Accordion>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="schema" pt="lg">
          <Paper shadow="sm" p="xl" withBorder>
            <Alert color="blue" icon={<AlertCircle size={18} />} mb="md">
              Attribute schema management coming soon. Currently showing {attributeDefs.length} zone attributes.
            </Alert>
            
            <Stack gap="sm">
              {Object.entries(groupedAttributes).map(([category, defs]) => (
                <div key={category}>
                  <Text fw={600} mb="xs">{category}</Text>
                  <Group gap="xs">
                    {defs.map((def) => (
                      <Badge key={def.id} variant="light">
                        {def.label} ({def.type})
                      </Badge>
                    ))}
                  </Group>
                </div>
              ))}
            </Stack>
          </Paper>
        </Tabs.Panel>
      </Tabs>

      {/* Add Zone Modal */}
      <Modal
        opened={addZoneModalOpen}
        onClose={() => {
          setAddZoneModalOpen(false);
          setNewZoneType('');
          setNewZoneName('');
        }}
        title="Add New Zone"
        size="md"
      >
        <Stack gap="md">
          <Select
            label="Room Type"
            placeholder="Select room type"
            value={newZoneType}
            onChange={(value) => setNewZoneType(value || '')}
            data={zoneSchema?.zone_types || []}
            searchable
            required
          />
          
          <TextInput
            label="Zone Name"
            placeholder="e.g., Master Bedroom, Guest Bathroom"
            value={newZoneName}
            onChange={(e) => setNewZoneName(e.currentTarget.value)}
            required
          />

          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={() => {
                setAddZoneModalOpen(false);
                setNewZoneType('');
                setNewZoneName('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAddZone}
              disabled={!newZoneType || !newZoneName}
            >
              Add Zone
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  );
}
