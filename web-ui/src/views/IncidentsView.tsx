
import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Badge,
  Loader,
  Stack,
  Title,
  Text,
  Card,
  Group,
  Collapse,
  Button,
  Textarea,
  Modal,
  ActionIcon,
  Divider,
  List,
  ScrollArea,
  Paper,
  SegmentedControl
} from '@mantine/core';
import {
  ChevronDown,
  ChevronUp,
  Brain,
  Phone,
  MessageSquare,
  Send,
  AlertCircle,
  CheckCircle,
  Eye,
  EyeOff,
  XCircle
} from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';
import ReactMarkdown from 'react-markdown';
import { API_BASE_WITH_PATHS } from '../apiConfig';

const API_BASE = API_BASE_WITH_PATHS;
// All AI routes are proxied through Go API at /api/ai/*

function getSeverityColor(severity?: string) {
  if (!severity || typeof severity !== 'string') return 'gray';
  switch (severity.toLowerCase()) {
    case 'critical': return 'red';
    case 'high': return 'orange';
    case 'medium': return 'yellow';
    case 'low': return 'blue';
    default: return 'gray';
  }
}

function getStatusIcon(status?: string) {
  switch (status?.toLowerCase()) {
    case 'resolved': return <CheckCircle size={16} />;
    case 'acknowledged': return <Eye size={16} />;
    case 'ignored': return <EyeOff size={16} />;
    default: return <AlertCircle size={16} />;
  }
}

function getStatusColor(status?: string) {
  switch (status?.toLowerCase()) {
    case 'resolved': return 'green';
    case 'acknowledged': return 'blue';
    case 'ignored': return 'gray';
    default: return 'red';
  }
}

interface AIRecommendation {
  analysis: string;
  insights: string[];
  actions?: string[];
  metadata?: any;
  loading?: boolean;
  error?: string;
}

export function IncidentsView() {
  const [incidents, setIncidents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('open'); // 'all', 'open', 'acknowledged', 'ignored', 'resolved'
  const [actionLoading, setActionLoading] = useState<Record<string, string>>({}); // track loading state per incident action
  const [recommendations, setRecommendations] = useState<Record<string, AIRecommendation>>({});
  const [chatModal, setChatModal] = useState<{open: boolean, incidentId: string | null}>({open: false, incidentId: null});
  const [chatMessages, setChatMessages] = useState<{role: 'user' | 'assistant', content: string}[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [technicianModal, setTechnicianModal] = useState<{open: boolean, incidentId: string | null}>({open: false, incidentId: null});
  const [technicianNotes, setTechnicianNotes] = useState('');
  const incidentsRef = useRef<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController>(new AbortController());
  const analysisAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    fetch(`${API_BASE}/incidents`, { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        const incidentList = data || [];
        setIncidents(incidentList);
        incidentsRef.current = incidentList;
        setLoading(false);
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          setLoading(false);
        }
      });

    // Cleanup: abort all pending requests when component unmounts
    return () => {
      controller.abort();
      if (analysisAbortControllerRef.current) {
        analysisAbortControllerRef.current.abort();
      }
    };
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages]);

  const fetchAIRecommendation = async (incident: any) => {
    const incidentId = incident.id;

    // Mark as loading
    setRecommendations(prev => ({
      ...prev,
      [incidentId]: { analysis: '', insights: ['Analysis in progress...'], loading: true }
    }));

    try {
      // Trigger re-analysis by calling analyze endpoint directly
      const response = await fetch(`${API_BASE}/ai/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'incident',
          data: {
            id: incident.id,
            type: incident.title || 'Unknown incident',
            severity: incident.severity,
            device_id: incident.device_id,
            description: incident.description
          },
          context: {
            incident_id: incident.id,
            device_id: incident.device_id
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        setRecommendations(prev => ({
          ...prev,
          [incidentId]: { ...data, loading: false }
        }));
      } else {
        throw new Error('AI service returned error');
      }
    } catch (error: any) {
      console.error('Failed to fetch AI recommendation:', error);
      setRecommendations(prev => ({
        ...prev,
        [incidentId]: {
          analysis: 'AI recommendations unavailable',
          insights: ['AI service is currently unavailable. Please check the connection.'],
          loading: false,
          error: 'Service unavailable'
        }
      }));
    }
  };

  // SSE event handling via callback subscription
  const handleEvent = useCallback((event: any) => {
    console.log('IncidentsView received event:', event);
    let updated = incidentsRef.current;
    if (event.type === "incident_added") {
      const exists = updated.some(i => i.id === event.data.id);
      if (!exists) {
        updated = [...updated, event.data];
        incidentsRef.current = updated;
        setIncidents(updated);
      }
    } else if (event.type === "incident_updated") {
      updated = updated.map(i => i.id === event.data.id ? event.data : i);
      incidentsRef.current = updated;
      setIncidents(updated);
    } else if (event.type === "incident_removed") {
      updated = updated.filter(i => i.id !== event.data.id);
      incidentsRef.current = updated;
      setIncidents(updated);
      // Remove from recommendations cache
      setRecommendations(prev => {
        const newRecs = { ...prev };
        delete newRecs[event.data.id];
        return newRecs;
      });
    } else if (event.type === "incident_analysis_completed") {
      // Update recommendations cache with completed analysis
      const incidentId = event.data.incident_id;
      setRecommendations(prev => ({
        ...prev,
        [incidentId]: {
          analysis: event.data.analysis || '',
          insights: event.data.insights || [],
          actions: event.data.actions || [],
          metadata: event.data.metadata || {},
          loading: false
        }
      }));
      // Refresh incident in list to update analysis_status
      fetch(`${API_BASE}/incidents/${incidentId}`)
        .then(res => res.json())
        .then(incident => {
          updated = updated.map(i => i.id === incidentId ? incident : i);
          incidentsRef.current = updated;
          setIncidents(updated);
        });
    } else if (event.type === "incident_analysis_failed") {
      // Handle analysis failure
      const incidentId = event.data.incident_id;
      setRecommendations(prev => ({
        ...prev,
        [incidentId]: {
          analysis: 'Analysis failed',
          insights: [event.data.error || 'Unknown error during analysis'],
          loading: false,
          error: event.data.error || 'Analysis error'
        }
      }));
      // Refresh incident in list
      fetch(`${API_BASE}/incidents/${incidentId}`)
        .then(res => res.json())
        .then(incident => {
          updated = updated.map(i => i.id === incidentId ? incident : i);
          incidentsRef.current = updated;
          setIncidents(updated);
        });
    }
  }, []);
  useEventSubscription(handleEvent);

  const handleChatSubmit = async () => {
    if (!chatInput.trim() || chatLoading) return;

    const incident = incidents.find(i => i.id === chatModal.incidentId);
    if (!incident) return;

    const userMessage = chatInput.trim();
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatInput('');
    setChatLoading(true);

    try {
      const response = await fetch(`${API_BASE}/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          context: {
            incident: {
              id: incident.id,
              title: incident.title,
              description: incident.description,
              severity: incident.severity,
              status: incident.status,
              device_id: incident.device_id,
              device_name: incident.device_name,
              sensor_id: incident.sensor_id,
              rule_name: incident.rule_name,
              zone_id: incident.zone_id,
              created_at: incident.created_at
            }
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        setChatMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
      } else {
        setChatMessages(prev => [...prev, {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.'
        }]);
      }
    } catch (error) {
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Unable to connect to AI service.'
      }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleCallTechnician = () => {
    const incident = incidents.find(i => i.id === technicianModal.incidentId);
    if (!incident) return;

    // In a real implementation, this would integrate with a dispatch system
    alert(`Technician dispatch request created for incident: ${incident.title}\n\nNotes: ${technicianNotes || 'None'}\n\nA technician will be contacted shortly.`);

    setTechnicianModal({open: false, incidentId: null});
    setTechnicianNotes('');
  };

  const handleAcknowledge = async (incidentId: string) => {
    setActionLoading(prev => ({ ...prev, [incidentId]: 'acknowledge' }));
    try {
      const response = await fetch(`${API_BASE}/incidents/${incidentId}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '' })
      });
      if (response.ok) {
        const updated = await response.json();
        setIncidents(prev => prev.map(i => i.id === incidentId ? updated : i));
        incidentsRef.current = incidentsRef.current.map(i => i.id === incidentId ? updated : i);
      }
    } catch (error) {
      console.error('Failed to acknowledge incident:', error);
    } finally {
      setActionLoading(prev => {
        const newState = { ...prev };
        delete newState[incidentId];
        return newState;
      });
    }
  };

  const handleIgnore = async (incidentId: string) => {
    setActionLoading(prev => ({ ...prev, [incidentId]: 'ignore' }));
    try {
      const response = await fetch(`${API_BASE}/incidents/${incidentId}/ignore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '' })
      });
      if (response.ok) {
        const updated = await response.json();
        setIncidents(prev => prev.map(i => i.id === incidentId ? updated : i));
        incidentsRef.current = incidentsRef.current.map(i => i.id === incidentId ? updated : i);
      }
    } catch (error) {
      console.error('Failed to ignore incident:', error);
    } finally {
      setActionLoading(prev => {
        const newState = { ...prev };
        delete newState[incidentId];
        return newState;
      });
    }
  };

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading incidents...</Text>
      </Stack>
    );
  }

  // Filter incidents based on status
  const filteredIncidents = statusFilter === 'all'
    ? incidents
    : statusFilter === 'active'
    ? incidents.filter((i: any) => i.status === 'open' || i.status === 'acknowledged')
    : incidents.filter((i: any) => i.status === statusFilter);

  // Separate active and closed incidents
  const activeIncidents = filteredIncidents.filter((i: any) => i.status === 'open' || i.status === 'acknowledged');
  const closedIncidents = filteredIncidents.filter((i: any) => i.status === 'resolved' || i.status === 'ignored');

  if (incidents.length === 0) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <CheckCircle size={64} color="#40c057" />
        <Title order={3}>No Incidents</Title>
        <Text c="dimmed">All systems operating normally</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Title order={2}>Incidents</Title>
          <Text size="sm" c="dimmed">
            {activeIncidents.length} active, {closedIncidents.length} closed
          </Text>
        </div>
        <SegmentedControl
          value={statusFilter}
          onChange={setStatusFilter}
          data={[
            { label: 'Active', value: 'active' },
            { label: 'Ignored', value: 'ignored' },
            { label: 'Resolved', value: 'resolved' },
            { label: 'All', value: 'all' },
          ]}
        />
      </Group>

      {activeIncidents.length > 0 && (
        <>
          <Title order={5} c="red" mt="md">Active Incidents</Title>
          <Stack gap="sm">
            {activeIncidents.map((incident: any) => {
          const isExpanded = expandedId === incident.id;
          const recommendation = recommendations[incident.id];

          return (
            <Card key={incident.id} withBorder padding="md" shadow="sm">
              <Stack gap="sm">
                <Group justify="space-between" wrap="nowrap">
                  <Group gap="sm">
                    {getStatusIcon(incident.status)}
                    <div>
                      <Text fw={600} size="md">{incident.title}</Text>
                      <Text size="xs" c="dimmed">
                        {incident.created_at && !isNaN(new Date(incident.created_at).getTime())
                          ? new Date(incident.created_at).toLocaleString()
                          : 'Unknown date'}
                        {incident.status === 'acknowledged' && incident.acknowledged_at && (
                          <> • Ack: {new Date(incident.acknowledged_at).toLocaleString()}</>
                        )}
                      </Text>
                    </div>
                  </Group>
                  <Group gap="xs">
                    <Badge color={getSeverityColor(incident.severity)}>{incident.severity}</Badge>
                    <Badge variant="light" color={getStatusColor(incident.status)}>{incident.status}</Badge>
                    {incident.type && <Badge color="grape" variant="dot">{incident.type.replace(/_/g, ' ')}</Badge>}
                    <ActionIcon
                      variant="subtle"
                      onClick={() => {
                        if (isExpanded) {
                          // Closing
                          setExpandedId(null);
                        } else {
                          // Opening - fetch analysis data from incident
                          setExpandedId(incident.id);
                          // Update recommendations from incident data
                          if (incident.analysis_status === 'completed') {
                            setRecommendations(prev => ({
                              ...prev,
                              [incident.id]: {
                                analysis: incident.analysis || '',
                                insights: incident.insights || [],
                                actions: incident.actions || [],
                                metadata: incident.analysis_data || {},
                                loading: false
                              }
                            }));
                          } else if (incident.analysis_status === 'pending') {
                            setRecommendations(prev => ({
                              ...prev,
                              [incident.id]: {
                                analysis: '',
                                insights: ['Analysis in progress...'],
                                loading: true
                              }
                            }));
                          } else if (incident.analysis_status === 'failed') {
                            setRecommendations(prev => ({
                              ...prev,
                              [incident.id]: {
                                analysis: 'Analysis failed',
                                insights: ['AI service encountered an error'],
                                loading: false,
                                error: 'Analysis error'
                              }
                            }));
                          }
                        }
                      }}
                    >
                      {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                    </ActionIcon>
                  </Group>
                </Group>

                <Text size="sm">{incident.description}</Text>

                {/* Device Metadata */}
                <Group gap="xs" wrap="wrap">
                  {incident.device_id && (
                    <Badge variant="dot" size="sm" color="gray">Device: {incident.device_id}</Badge>
                  )}
                  {incident.sensor_id && (
                    <Badge variant="dot" size="sm" color="gray">Sensor: {incident.sensor_id}</Badge>
                  )}
                  {incident.rule_name && (
                    <Badge variant="dot" size="sm" color="blue">Rule: {incident.rule_name}</Badge>
                  )}
                  {incident.zone_id && incident.zone_id !== "N/A" && (
                    <Badge variant="dot" size="sm" color="teal">Zone: {incident.zone_id}</Badge>
                  )}
                </Group>

                <Collapse in={isExpanded}>
                  <Stack gap="md" mt="md">
                    <Divider />

                    {/* AI Recommendations Section */}
                    <Paper p="md" withBorder style={{ backgroundColor: 'var(--mantine-color-blue-0)' }}>
                      <Group gap="xs" mb="sm" justify="space-between">
                        <Group gap="xs">
                          <Brain size={20} color="#228be6" />
                          <Text fw={600} size="sm">AI Analysis & Recommendations</Text>
                        </Group>
                        {recommendation && !recommendation.loading && (
                          <Button
                            size="xs"
                            variant="subtle"
                            onClick={() => fetchAIRecommendation(incident)}
                          >
                            Re-analyze
                          </Button>
                        )}
                      </Group>

                      {recommendation?.loading ? (
                        <Group gap="xs">
                          <Loader size="sm" />
                          <Text size="sm" c="dimmed">Analyzing incident...</Text>
                        </Group>
                      ) : recommendation?.error ? (
                        <Text size="sm" c="red">{recommendation.insights[0]}</Text>
                      ) : recommendation ? (
                        <Stack gap="sm">
                          {/* Documentation Status Warning */}
                          {recommendation.metadata?.documentation_available === false && (
                            <Paper p="xs" withBorder style={{ backgroundColor: 'var(--mantine-color-yellow-0)', borderColor: 'var(--mantine-color-yellow-3)' }}>
                              <Group gap="xs">
                                <AlertCircle size={16} color="var(--mantine-color-yellow-7)" />
                                <Text size="xs" c="yellow.9">
                                  ⚠️ No device-specific documentation in knowledge base. Recommendations are generic.
                                </Text>
                              </Group>
                            </Paper>
                          )}

                          <Text size="sm">{recommendation.analysis}</Text>

                          {recommendation.insights && recommendation.insights.length > 0 && (
                            <div>
                              <Text size="sm" fw={600} mb={4}>Insights:</Text>
                              <List size="sm" spacing={4}>
                                {recommendation.insights.map((insight, idx) => (
                                  <List.Item key={idx}>{insight}</List.Item>
                                ))}
                              </List>
                            </div>
                          )}

                          {recommendation.actions && recommendation.actions.length > 0 && (
                            <div>
                              <Text size="sm" fw={600} mb={4}>Recommended Actions:</Text>
                              <List size="sm" spacing={4} type="ordered">
                                {recommendation.actions.map((action, idx) => (
                                  <List.Item key={idx}>{action}</List.Item>
                                ))}
                              </List>
                            </div>
                          )}

                          {/* Sources Section */}
                          {recommendation.metadata?.sources_cited && recommendation.metadata.sources_cited.length > 0 && (
                            <div>
                              <Text size="xs" fw={600} mb={4} c="dimmed">Sources Referenced:</Text>
                              <Group gap="xs">
                                {recommendation.metadata.sources_cited.map((source: string, idx: number) => (
                                  <Badge key={idx} variant="light" size="xs" color="blue">
                                    {source}
                                  </Badge>
                                ))}
                              </Group>
                            </div>
                          )}

                          {/* RAG Sources (if available) */}
                          {recommendation.metadata?.rag_sources && recommendation.metadata.rag_sources.length > 0 && (
                            <div>
                              <Text size="xs" fw={600} mb={4} c="dimmed">Knowledge Base Sources:</Text>
                              <Stack gap={4}>
                                {recommendation.metadata.rag_sources.map((source: any, idx: number) => (
                                  <Text key={idx} size="xs" c="dimmed">
                                    • {source.source} (relevance: {Math.round(source.relevance * 100)}%)
                                  </Text>
                                ))}
                              </Stack>
                            </div>
                          )}
                        </Stack>
                      ) : (
                        <Text size="sm" c="dimmed">No recommendations available</Text>
                      )}
                    </Paper>

                    {/* Action Buttons */}
                    <Group gap="xs">
                      <Button
                        leftSection={<MessageSquare size={16} />}
                        variant="light"
                        size="xs"
                        disabled={recommendation?.loading}
                        title={recommendation?.loading ? 'Chat will be available once analysis is complete' : ''}
                        onClick={() => {
                          setChatModal({open: true, incidentId: incident.id});
                          setChatMessages([{
                            role: 'assistant',
                            content: `I'm here to help with "${incident.title}". What would you like to know?`
                          }]);
                        }}
                      >
                        {recommendation?.loading ? (
                          <>
                            <Loader size={14} style={{ marginRight: 8 }} />
                            Analyzing...
                          </>
                        ) : (
                          'Chat with AI'
                        )}
                      </Button>
                      <Button
                        leftSection={<Phone size={16} />}
                        variant="light"
                        color="orange"
                        size="xs"
                        onClick={() => setTechnicianModal({open: true, incidentId: incident.id})}
                      >
                        Call Technician
                      </Button>
                      {incident.status === 'open' && (
                        <Button
                          leftSection={actionLoading[incident.id] === 'acknowledge' ? <Loader size={14} /> : <Eye size={16} />}
                          variant="light"
                          color="blue"
                          size="xs"
                          disabled={!!actionLoading[incident.id]}
                          onClick={() => handleAcknowledge(incident.id)}
                        >
                          Acknowledge
                        </Button>
                      )}
                      {(incident.status === 'open' || incident.status === 'acknowledged') && (
                        <Button
                          leftSection={actionLoading[incident.id] === 'ignore' ? <Loader size={14} /> : <XCircle size={16} />}
                          variant="light"
                          color="gray"
                          size="xs"
                          disabled={!!actionLoading[incident.id]}
                          onClick={() => handleIgnore(incident.id)}
                        >
                          Dismiss
                        </Button>
                      )}
                    </Group>

                    <Divider />

                    {/* Incident Details */}
                    <Group gap="xl">
                      <div>
                        <Text size="xs" c="dimmed">Device ID</Text>
                        <Text size="sm">{incident.device_id || 'N/A'}</Text>
                      </div>
                      <div>
                        <Text size="xs" c="dimmed">Zone</Text>
                        <Text size="sm">{incident.zone_id || 'N/A'}</Text>
                      </div>
                      <div>
                        <Text size="xs" c="dimmed">Rule</Text>
                        <Text size="sm">{incident.rule_name || 'N/A'}</Text>
                      </div>
                    </Group>
                  </Stack>
                </Collapse>
              </Stack>
            </Card>
          );
        })}
      </Stack>
      </>
      )}

      {closedIncidents.length > 0 && (
        <>
          <Title order={5} c="dimmed" mt="xl">Closed Incidents</Title>
          <Stack gap="sm">
            {closedIncidents.map((incident: any) => {
              const closedAt = incident.status === 'resolved' ? incident.resolved_at :
                              incident.status === 'ignored' ? incident.ignored_at : null;
              const closedLabel = incident.status === 'resolved' ? 'Resolved' : 'Dismissed';
              return (
                <Card key={incident.id} withBorder padding="md" shadow="sm" opacity={0.7}>
                  <Stack gap="sm">
                    <Group justify="space-between" wrap="nowrap">
                      <Group gap="sm">
                        {getStatusIcon(incident.status)}
                        <div>
                          <Text fw={600} size="md">{incident.title}</Text>
                          <Text size="xs" c="dimmed">
                            {closedLabel}: {closedAt && !isNaN(new Date(closedAt).getTime())
                              ? new Date(closedAt).toLocaleString()
                              : 'Unknown'}
                          </Text>
                        </div>
                      </Group>
                      <Group gap="xs">
                        <Badge color={getSeverityColor(incident.severity)}>{incident.severity}</Badge>
                        <Badge variant="light" color={getStatusColor(incident.status)}>{incident.status}</Badge>
                        {incident.type && <Badge color="grape" variant="dot">{incident.type.replace(/_/g, ' ')}</Badge>}
                      </Group>
                    </Group>
                    <Text size="sm">{incident.description}</Text>
                    {incident.notes && (
                      <Text size="xs" c="dimmed" fs="italic">Notes: {incident.notes}</Text>
                    )}
                  </Stack>
                </Card>
              );
            })}
          </Stack>
        </>
      )}

      {/* AI Chat Modal */}
      <Modal
        opened={chatModal.open}
        onClose={() => setChatModal({open: false, incidentId: null})}
        title={
          <Group gap="xs">
            <Brain size={20} />
            <Text fw={600}>AI Assistant</Text>
          </Group>
        }
        size="lg"
      >
        <Stack gap="md">
          <ScrollArea h={400} style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 4, padding: 12 }}>
            <Stack gap="sm">
              {chatMessages.map((msg, idx) => (
                <Paper
                  key={idx}
                  p="sm"
                  style={{
                    backgroundColor: msg.role === 'user' ? 'var(--mantine-color-blue-1)' : 'var(--mantine-color-gray-1)',
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%'
                  }}
                >
                  {msg.role === 'assistant' ? (
                    <div style={{ whiteSpace: 'pre-wrap' }}>
                      <ReactMarkdown
                        children={msg.content}
                        components={{
                          p: ({children}: any) => <Text size="sm">{children}</Text>,
                          li: ({children}: any) => <li style={{ marginLeft: 8 }}>{children}</li>,
                          strong: ({children}: any) => <Text component="span" fw={700}>{children}</Text>
                        }}
                      />
                    </div>
                  ) : (
                    <Text size="sm">{msg.content}</Text>
                  )}
                </Paper>
              ))}
              {chatLoading && (
                <Group gap="xs">
                  <Loader size="xs" />
                  <Text size="sm" c="dimmed">AI is thinking...</Text>
                </Group>
              )}
              <div ref={messagesEndRef} />
            </Stack>
          </ScrollArea>

          <Group gap="xs" align="flex-end">
            <Textarea
              placeholder="Ask a question about this incident..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleChatSubmit();
                }
              }}
              style={{ flex: 1 }}
              minRows={2}
              maxRows={4}
            />
            <Button
              onClick={handleChatSubmit}
              disabled={!chatInput.trim() || chatLoading}
              leftSection={<Send size={16} />}
            >
              Send
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Technician Dispatch Modal */}
      <Modal
        opened={technicianModal.open}
        onClose={() => setTechnicianModal({open: false, incidentId: null})}
        title={
          <Group gap="xs">
            <Phone size={20} />
            <Text fw={600}>Call Technician</Text>
          </Group>
        }
      >
        <Stack gap="md">
          <Text size="sm">
            This will create a dispatch request for a technician to investigate and resolve this incident.
          </Text>

          <Textarea
            label="Additional Notes (optional)"
            placeholder="Provide any additional context for the technician..."
            value={technicianNotes}
            onChange={(e) => setTechnicianNotes(e.target.value)}
            minRows={3}
          />

          <Group justify="flex-end" gap="xs">
            <Button variant="subtle" onClick={() => setTechnicianModal({open: false, incidentId: null})}>
              Cancel
            </Button>
            <Button onClick={handleCallTechnician} leftSection={<Phone size={16} />}>
              Request Technician
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
