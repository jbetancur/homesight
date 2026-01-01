import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE_WITH_PATHS } from '../apiConfig';
import { useEventSubscription } from '../useEventSubscription';

export interface Incident {
  id: string;
  type: string;
  title: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'open' | 'acknowledged' | 'ignored' | 'resolved';
  device_id: string;
  zone_id?: string;
  created_at: string;
  updated_at: string;
  analysis?: string;
  insights?: string[];
  actions?: string[];
}

interface AlertsContextValue {
  incidents: Incident[];
  activeIncidents: Incident[];
  hasActiveAlerts: boolean;
  criticalCount: number;
  warningCount: number;
  loading: boolean;
  acknowledgeIncident: (id: string) => Promise<void>;
  dismissIncident: (id: string) => Promise<void>;
  getDeviceIncidents: (deviceId: string) => Incident[];
  hasDeviceAlert: (deviceId: string) => boolean;
  refetch: () => Promise<void>;
}

const AlertsContext = createContext<AlertsContextValue | null>(null);

export function useAlerts(): AlertsContextValue {
  const ctx = useContext(AlertsContext);
  if (!ctx) {
    throw new Error('useAlerts must be used within AlertsProvider');
  }
  return ctx;
}

export const AlertsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const incidentsRef = useRef<Incident[]>([]);

  // Keep ref in sync for SSE callbacks
  useEffect(() => {
    incidentsRef.current = incidents;
  }, [incidents]);

  const fetchIncidents = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_WITH_PATHS}/incidents`);
      if (response.ok) {
        const data = await response.json();
        setIncidents(data || []);
      }
    } catch (err) {
      console.error('Failed to fetch incidents:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  // SSE event handler
  const handleEvent = useCallback((event: { type: string; data: any }) => {
    switch (event.type) {
      case 'incident_added':
        setIncidents(prev => {
          if (prev.some(i => i.id === event.data.id)) return prev;
          return [event.data, ...prev];
        });
        break;
      case 'incident_updated':
        setIncidents(prev =>
          prev.map(i => (i.id === event.data.id ? { ...i, ...event.data } : i))
        );
        break;
      case 'incident_removed':
        setIncidents(prev => prev.filter(i => i.id !== event.data.id));
        break;
    }
  }, []);

  useEventSubscription(handleEvent);

  const acknowledgeIncident = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API_BASE_WITH_PATHS}/incidents/${id}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '' }),
      });
      if (response.ok) {
        const updated = await response.json();
        setIncidents(prev => prev.map(i => (i.id === id ? updated : i)));
      }
    } catch (err) {
      console.error('Failed to acknowledge incident:', err);
    }
  }, []);

  const dismissIncident = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API_BASE_WITH_PATHS}/incidents/${id}/ignore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '' }),
      });
      if (response.ok) {
        const updated = await response.json();
        setIncidents(prev => prev.map(i => (i.id === id ? updated : i)));
      }
    } catch (err) {
      console.error('Failed to dismiss incident:', err);
    }
  }, []);

  const getDeviceIncidents = useCallback(
    (deviceId: string) => incidents.filter(i => i.device_id === deviceId),
    [incidents]
  );

  const hasDeviceAlert = useCallback(
    (deviceId: string) =>
      incidents.some(
        i => i.device_id === deviceId && (i.status === 'open' || i.status === 'acknowledged')
      ),
    [incidents]
  );

  // Derived state
  const activeIncidents = incidents.filter(
    i => i.status === 'open' || i.status === 'acknowledged'
  );
  const hasActiveAlerts = activeIncidents.length > 0;
  const criticalCount = activeIncidents.filter(
    i => i.severity === 'critical' || i.severity === 'high'
  ).length;
  const warningCount = activeIncidents.filter(
    i => i.severity === 'medium' || i.severity === 'low'
  ).length;

  const value: AlertsContextValue = {
    incidents,
    activeIncidents,
    hasActiveAlerts,
    criticalCount,
    warningCount,
    loading,
    acknowledgeIncident,
    dismissIncident,
    getDeviceIncidents,
    hasDeviceAlert,
    refetch: fetchIncidents,
  };

  return <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>;
};
