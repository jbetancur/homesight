
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { AppShell, Group, Stack, Text, Button, rem } from '@mantine/core';
import { Home, AlertCircle, Search, Activity, Settings } from 'lucide-react';
import { DevicesView } from './views/DevicesView';
import { IncidentsView } from './views/IncidentsView';
import { DiscoveryView } from './views/DiscoveryView';

function App() {
  return (
    <Router>
      <AppShell
        padding="md"
        navbar={{
          width: 260,
          breakpoint: 'sm',
          collapsed: { mobile: false },
        }}
        header={{ height: 60 }}
        layout="alt"
        style={{ minHeight: '100vh' }}
      >
        <AppShell.Navbar p="md" style={{ background: 'var(--mantine-color-blue-light)' }}>
          <Stack gap={16} justify="flex-start" style={{ height: '100%' }}>
            <Group mb={rem(24)}>
              <Home size={32} color="#228be6" />
              <Text size="xl" fw={700} c="blue.7">HomeSight</Text>
            </Group>
            <Button fullWidth component={Link} to="/" variant="light" color="blue" leftSection={<Activity size={18} />}>Devices</Button>
            <Button fullWidth component={Link} to="/incidents" variant="light" color="blue" leftSection={<AlertCircle size={18} />}>Incidents</Button>
            <Button fullWidth component={Link} to="/discovery" variant="light" color="blue" leftSection={<Search size={18} />}>Discovery</Button>
            <Group mt="auto">
              <Settings size={22} color="#868e96" />
              <Text size="sm" c="dimmed">Settings</Text>
            </Group>
          </Stack>
        </AppShell.Navbar>
        <AppShell.Header p="xs" style={{ background: 'var(--mantine-color-blue-light)' }}>
          <Group justify="space-between" style={{ height: '100%' }}>
            <Group>
              <Text size="xl" fw={700} c="blue.7">HomeSight Admin Dashboard</Text>
            </Group>
            <Group>
              <Text size="sm" c="dimmed">Welcome!</Text>
            </Group>
          </Group>
        </AppShell.Header>
        <AppShell.Main style={{ width: '100%', overflowX: 'auto' }}>
          <Routes>
            <Route path="/" element={<DevicesView />} />
            <Route path="/incidents" element={<IncidentsView />} />
            <Route path="/discovery" element={<DiscoveryView />} />
          </Routes>
        </AppShell.Main>
      </AppShell>
    </Router>
  );
}

export default App;
