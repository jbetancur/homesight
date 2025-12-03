
import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { AppShell, Group, Stack, Text, Container, Burger } from '@mantine/core';
import { Home, AlertCircle, Activity, Settings, Server, LogOut, Layers, Brain } from 'lucide-react';
import { DevicesView } from './views/DevicesView';
import { DeviceOverviewView } from './views/DeviceOverviewView';
import { SensorDetailView } from './views/SensorDetailView';
import { IncidentsView } from './views/IncidentsView';
import { IntegrationsView } from './views/IntegrationsView';
import { StatusView } from './views/StatusView';
import { ZWaveView } from './views/ZWaveView';
import HSILRoomView from './views/HSILRoomView';
import FloatingAIAssistant from './components/FloatingAIAssistant';
import FloatingAIButton from './components/FloatingAIButton';
import './App.css';

const navItems = [
  { label: 'Devices', icon: Activity, path: '/' },
  { label: 'Home Intelligence', icon: Brain, path: '/hsil' },
  { label: 'Incidents', icon: AlertCircle, path: '/incidents' },
  { label: 'Integrations', icon: Layers, path: '/integrations' },
  { label: 'Status', icon: Server, path: '/status' },
];

function NavLink({ label, icon: Icon, path, isActive }: { label: string; icon: any; path: string; isActive: boolean }) {
  return (
    <Link to={path} style={{ textDecoration: 'none' }}>
      <Group gap="xs" className={`nav-link ${isActive ? 'active' : ''}`}>
        <Icon size={20} />
        <span>{label}</span>
      </Group>
    </Link>
  );
}

function NavbarContent() {
  const location = useLocation();

  return (
    <>
      <div className="navbar-main">
        <Group gap="sm" className="navbar-header">
          <Home size={28} color="#228be6" />
          <Text size="lg" fw={700} c="blue.7">HomeSight</Text>
        </Group>

        <Stack gap={0} className="navbar-links">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              label={item.label}
              icon={item.icon}
              path={item.path}
              isActive={location.pathname === item.path}
            />
          ))}
        </Stack>
      </div>

      <div className="navbar-footer">
        <a href="#" className="nav-link" onClick={(e) => e.preventDefault()}>
          <Group gap="xs">
            <Settings size={20} />
            <span>Settings</span>
          </Group>
        </a>
        <a href="#" className="nav-link" onClick={(e) => e.preventDefault()}>
          <Group gap="xs">
            <LogOut size={20} />
            <span>Logout</span>
          </Group>
        </a>
      </div>
    </>
  );
}

function AppContent() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false);

  return (
    <>
      <AppShell
        navbar={{
          width: 260,
          breakpoint: 'sm',
          collapsed: { mobile: !mobileMenuOpen, desktop: false },
        }}
        header={{ height: 56 }}
        layout="alt"
        style={{ minHeight: '100vh' }}
      >
      <AppShell.Navbar p={0} className="navbar">
        <NavbarContent />
      </AppShell.Navbar>
      <AppShell.Header p="0" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)', background: 'white' }}>
        <Group
          justify="space-between"
          h="100%"
          px="md"
          py={0}
        >
          <Burger
            opened={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            hiddenFrom="sm"
            size="sm"
          />
          <Text size="md" fw={700}>HomeSight Admin Dashboard</Text>
          <div style={{ width: 40 }} />
        </Group>
      </AppShell.Header>
      <AppShell.Main style={{ width: '100%', overflowX: 'auto' }}>
        <Container size="xl" py="md">
          <Routes>
            <Route path="/" element={<DevicesView />} />
            <Route path="/hsil" element={<HSILRoomView />} />
            <Route path="/devices/:deviceId/overview" element={<DeviceOverviewView />} />
            <Route path="/devices/:deviceId/sensors/:sensorId" element={<SensorDetailView />} />
            <Route path="/incidents" element={<IncidentsView />} />
            <Route path="/integrations" element={<IntegrationsView />} />
            <Route path="/integrations/zwave" element={<ZWaveView />} />
            <Route path="/status" element={<StatusView />} />
          </Routes>
        </Container>
      </AppShell.Main>
    </AppShell>

      {/* Global Floating AI Assistant */}
      {!aiAssistantOpen && (
        <FloatingAIButton onClick={() => setAiAssistantOpen(true)} />
      )}
      <FloatingAIAssistant
        opened={aiAssistantOpen}
        onClose={() => setAiAssistantOpen(false)}
      />
    </>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
