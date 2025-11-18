import { useState, useEffect } from 'react'
import { Home, AlertCircle, Search, Activity, Settings } from 'lucide-react'
import './App.css'

const API_BASE = 'http://localhost:8080/api'

interface Device {
  id: string
  name: string
  type: string
  integration: string
  metadata?: Record<string, string>
}

interface Incident {
  ID: string
  Title: string
  Description: string
  Severity: string
  Status: string
  DeviceID: string
  CreatedAt: string
}

interface DiscoveryDevice {
  id: string
  name: string
  type: string
  host?: string
  manufacturer?: string
  model?: string
}

function App() {
  const [activeTab, setActiveTab] = useState<'devices' | 'incidents' | 'discovery'>('devices')
  const [devices, setDevices] = useState<Device[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [discovery, setDiscovery] = useState<DiscoveryDevice[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Hydrate initial state with API calls
    Promise.all([
      fetch(`${API_BASE}/devices`).then(res => res.json()),
      fetch(`${API_BASE}/incidents`).then(res => res.json()),
      fetch(`${API_BASE}/discovery`).then(res => res.json())
    ]).then(([devicesData, incidentsData, discoveryData]) => {
      setDevices(devicesData || [])
      setIncidents(incidentsData || [])
      setDiscovery(discoveryData?.devices || [])
      setLoading(false)
    }).catch((err) => {
      console.error('Initial hydration error:', err)
      setLoading(false)
    })

    // Subscribe to SSE for live updates (delta events)
    const es = new EventSource(`${API_BASE}/events`)
    es.onmessage = (event) => {
      try {
        const evt = JSON.parse(event.data)
        switch (evt.type) {
          case 'device_added':
            setDevices(prev => {
              const exists = prev.find(d => d.id === evt.data.id)
              return exists ? prev : [...prev, evt.data]
            })
            break
          case 'device_removed':
            setDevices(prev => prev.filter(d => d.id !== evt.data.id))
            break
          case 'device_updated':
            setDevices(prev => prev.map(d => d.id === evt.data.id ? evt.data : d))
            break
          case 'incident_added':
            setIncidents(prev => {
              const exists = prev.find(i => i.ID === evt.data.ID)
              return exists ? prev : [...prev, evt.data]
            })
            break
          case 'incident_removed':
            setIncidents(prev => prev.filter(i => i.ID !== evt.data.id))
            break
          case 'incident_updated':
            setIncidents(prev => prev.map(i => i.ID === evt.data.ID ? evt.data : i))
            break
          default:
            // Ignore unknown event types
            break
        }
      } catch (err) {
        console.error('SSE event error:', err)
      }
    }
    es.onerror = (err) => {
      console.error('SSE connection error:', err)
      es.close()
    }
    return () => es.close()
  }, [])

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-200'
      case 'high': return 'bg-orange-100 text-orange-800 border-orange-200'
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'low': return 'bg-blue-100 text-blue-800 border-blue-200'
      default: return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-3">
              <Home className="w-8 h-8 text-blue-600" />
              <h1 className="text-2xl font-bold text-gray-900">HomeSight</h1>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-500">
                {devices.length} devices · {incidents.filter(i => i.Status === 'active').length} active incidents
              </span>
              <Settings className="w-5 h-5 text-gray-400 cursor-pointer hover:text-gray-600" />
            </div>
          </div>
        </div>
      </header>

      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab('devices')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${ activeTab === 'devices' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            >
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4" />
                <span>Devices</span>
              </div>
            </button>
            <button
              onClick={() => setActiveTab('incidents')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'incidents' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            >
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-4 h-4" />
                <span>Incidents</span>
                {incidents.filter(i => i.Status === 'active').length > 0 && (
                  <span className="ml-2 bg-red-100 text-red-600 text-xs font-bold px-2 py-0.5 rounded-full">
                    {incidents.filter(i => i.Status === 'active').length}
                  </span>
                )}
              </div>
            </button>
            <button
              onClick={() => setActiveTab('discovery')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'discovery' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            >
              <div className="flex items-center space-x-2">
                <Search className="w-4 h-4" />
                <span>Discovery</span>
              </div>
            </button>
          </nav>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <>
            {activeTab === 'devices' && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {devices.length === 0 ? (
                  <div className="col-span-full text-center py-12 text-gray-500">
                    No devices found. Start discovering devices...
                  </div>
                ) : (
                  devices.map((device) => (
                    <div key={device.id} className="bg-white rounded-lg shadow border border-gray-200 p-6 hover:shadow-md transition-shadow">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900">{device.name}</h3>
                          <p className="text-sm text-gray-500 mt-1">{device.type}</p>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Online
                        </span>
                      </div>
                      <div className="mt-4 space-y-2">
                        <div className="text-sm">
                          <span className="text-gray-500">Integration:</span>
                          <span className="ml-2 font-medium text-gray-900">{device.integration}</span>
                        </div>
                        {device.metadata?.manufacturer && (
                          <div className="text-sm">
                            <span className="text-gray-500">Manufacturer:</span>
                            <span className="ml-2 font-medium text-gray-900">{device.metadata.manufacturer}</span>
                          </div>
                        )}
                        {device.metadata?.model && (
                          <div className="text-sm">
                            <span className="text-gray-500">Model:</span>
                            <span className="ml-2 font-medium text-gray-900">{device.metadata.model}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {activeTab === 'incidents' && (
              <div className="space-y-4">
                {incidents.length === 0 ? (
                  <div className="text-center py-12 text-gray-500 bg-white rounded-lg border border-gray-200">
                    No incidents. Your home is looking good! 🏠
                  </div>
                ) : (
                  incidents.map((incident) => (
                    <div key={incident.ID} className={`bg-white rounded-lg shadow border p-6 ${getSeverityColor(incident.Severity)}`}>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3">
                            <AlertCircle className="w-5 h-5" />
                            <h3 className="text-lg font-semibold">{incident.Title}</h3>
                          </div>
                          <p className="mt-2 text-sm">{incident.Description}</p>
                          <div className="mt-4 flex items-center space-x-4 text-sm">
                            <span className="font-medium">Device: {incident.DeviceID}</span>
                            <span className="text-gray-500">·</span>
                            <span className="text-gray-600">{new Date(incident.CreatedAt).toLocaleString()}</span>
                          </div>
                        </div>
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase ${incident.Status === 'active' ? 'bg-red-600 text-white' : 'bg-gray-300 text-gray-700'}`}>
                          {incident.Status}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {activeTab === 'discovery' && (
              <div className="space-y-4">
                {discovery.length === 0 ? (
                  <div className="text-center py-12 text-gray-500 bg-white rounded-lg border border-gray-200">
                    No new devices discovered. Run discovery scan...
                  </div>
                ) : (
                  discovery.map((device) => (
                    <div key={device.id} className="bg-white rounded-lg shadow border border-gray-200 p-6 hover:shadow-md transition-shadow">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900">{device.name || device.id}</h3>
                          <p className="text-sm text-gray-500 mt-1">{device.type}</p>
                          {device.host && <p className="text-sm text-gray-400 mt-1">Host: {device.host}</p>}
                        </div>
                        <button className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors">
                          Add Device
                        </button>
                      </div>
                      {(device.manufacturer || device.model) && (
                        <div className="mt-4 flex items-center space-x-4 text-sm text-gray-600">
                          {device.manufacturer && <span>{device.manufacturer}</span>}
                          {device.manufacturer && device.model && <span>·</span>}
                          {device.model && <span>{device.model}</span>}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default App
