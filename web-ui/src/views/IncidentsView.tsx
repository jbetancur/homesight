
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
  Paper
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
  Clock
} from 'lucide-react';
import { useEventSubscription } from '../useEventSubscription';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';

const API_BASE = 'http://localhost:8080/api';
// AI routes are now proxied through Go API at /api/ai/*

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
    case 'acknowledged': return <Clock size={16} />;
    default: return <AlertCircle size={16} />;
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
  const [recommendations, setRecommendations] = useState<Record<string, AIRecommendation>>({});
  const [chatModal, setChatModal] = useState<{open: boolean, incidentId: string | null}>({open: false, incidentId: null});
  const [chatMessages, setChatMessages] = useState<{role: 'user' | 'assistant', content: string}[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [technicianModal, setTechnicianModal] = useState<{open: boolean, incidentId: string | null}>({open: false, incidentId: null});
  const [technicianNotes, setTechnicianNotes] = useState('');
  const incidentsRef = useRef<any[]>([]);

  useEffect(() => {
    fetch(`${API_BASE}/incidents`).then(res => res.json()).then(data => {
      const incidentList = data || [];
      setIncidents(incidentList);
      incidentsRef.current = incidentList;
      setLoading(false);

      // Auto-fetch AI recommendations for all incidents
      incidentList.forEach((incident: any) => {
        if (incident.id) {
          fetchAIRecommendation(incident);
        }
      });
    }).catch(() => setLoading(false));
  }, []);

  const fetchAIRecommendation = async (incident: any) => {
    const incidentId = incident.id;

    // Mark as loading
    setRecommendations(prev => ({
      ...prev,
      [incidentId]: { analysis: '', insights: [], loading: true }
    }));

    try {
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
    } catch (error) {
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
        // Fetch AI recommendation for new incident
        fetchAIRecommendation(event.data);
      }
    } else if (event.type === "incident_updated") {
      updated = updated.map(i => i.id === event.data.id ? event.data : i);
      incidentsRef.current = updated;
      setIncidents(updated);
    } else if (event.type === "incident_removed") {
      updated = updated.filter(i => i.id !== event.data.id);
      incidentsRef.current = updated;
      setIncidents(updated);
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
              severity: incident.severity
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

  if (loading) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Loader size="lg" color="blue" />
        <Text c="dimmed">Loading incidents...</Text>
      </Stack>
    );
  }

  if (incidents.length === 0) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <CheckCircle size={64} color="#40c057" />
        <Title order={3}>No Active Incidents</Title>
        <Text c="dimmed">All systems operating normally</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Title order={2}>Incidents</Title>
          <Text size="sm" c="dimmed">{incidents.length} active incident{incidents.length !== 1 ? 's' : ''}</Text>
        </div>
      </Group>

      <Stack gap="sm">
        {incidents.map((incident: any) => {
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
                      </Text>
                    </div>
                  </Group>
                  <Group gap="xs">
                    <Badge color={getSeverityColor(incident.severity)}>{incident.severity}</Badge>
                    <Badge variant="light">{incident.status}</Badge>
                    <ActionIcon
                      variant="subtle"
                      onClick={() => setExpandedId(isExpanded ? null : incident.id)}
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
                      <Group gap="xs" mb="sm">
                        <Brain size={20} color="#228be6" />
                        <Text fw={600} size="sm">AI Analysis & Recommendations</Text>
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
                        onClick={() => {
                          setChatModal({open: true, incidentId: incident.id});
                          setChatMessages([{
                            role: 'assistant',
                            content: `I'm here to help with "${incident.title}". What would you like to know?`
                          }]);
                        }}
                      >
                        Chat with AI
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
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeSanitize]}
                        children={msg.content}
                        components={{
                          p: ({node, ...props}) => <Text size="sm" {...props} />,
                          li: ({node, ...props}) => <li style={{ marginLeft: 8 }} {...props} />,
                          strong: ({node, ...props}) => <Text component="span" fw={700} {...props} />
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
