import { useState, useEffect, useRef } from 'react';
import {
  Paper,
  Stack,
  Group,
  Text,
  Textarea,
  Button,
  ThemeIcon,
  ActionIcon,
  Box,
  Badge,
  Transition,
  rem,
} from '@mantine/core';
import {
  Brain,
  Send,
  X,
  Maximize2,
  Minimize2,
  Sparkles,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { API_BASE } from '../apiConfig';

interface AIMessage {
  role: 'user' | 'assistant';
  content: string;
  action?: any;
}

interface FloatingAIAssistantProps {
  opened: boolean;
  onClose: () => void;
}

export default function FloatingAIAssistant({ opened, onClose }: FloatingAIAssistantProps) {
  const [chatMessages, setChatMessages] = useState<AIMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [aiThinking, setAiThinking] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Generate a persistent session ID for this browser tab
  const [sessionId] = useState(() => {
    const stored = sessionStorage.getItem('hsil_session_id');
    if (stored) return stored;
    const newId = `session_${Date.now()}_${Math.random().toString(36).substring(7)}`;
    sessionStorage.setItem('hsil_session_id', newId);
    return newId;
  });

  useEffect(() => {
    // Auto-scroll to latest message
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const handleChatSubmit = async () => {
    if (!chatInput.trim()) return;

    const userMessage: AIMessage = { role: 'user', content: chatInput };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput('');
    setChatLoading(true);
    setAiThinking(true);

    try {
      const res = await fetch(`${API_BASE}/api/hsil/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: chatInput, session_id: sessionId }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMessage: AIMessage = {
          role: 'assistant',
          content: data.reply,
          action: data.action,
        };
        setChatMessages((prev) => [...prev, assistantMessage]);

        if (data.action) {
          setAiThinking(false);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: AIMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setChatLoading(false);
      setAiThinking(false);
    }
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  const handleExampleClick = async (question: string) => {
    // Submit directly with the question
    const userMessage: AIMessage = { role: 'user', content: question };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput('');
    setChatLoading(true);
    setAiThinking(true);

    try {
      const res = await fetch(`${API_BASE}/api/hsil/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, session_id: sessionId }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMessage: AIMessage = {
          role: 'assistant',
          content: data.reply,
          action: data.action,
        };
        setChatMessages((prev) => [...prev, assistantMessage]);

        if (data.action) {
          setAiThinking(false);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: AIMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setChatLoading(false);
      setAiThinking(false);
    }
  };

  return (
    <Transition
      mounted={opened}
      transition="slide-up"
      duration={300}
      timingFunction="ease"
    >
      {(styles) => (
        <Paper
          style={{
            ...styles,
            position: 'fixed',
            bottom: 20,
            right: 20,
            width: isExpanded ? 'min(700px, calc(100vw - 40px))' : 'min(450px, calc(100vw - 40px))',
            height: isExpanded ? 'calc(100vh - 100px)' : 'min(600px, calc(100vh - 80px))',
            maxHeight: 'calc(100vh - 80px)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.3)',
            transition: 'width 0.3s ease, height 0.3s ease',
          }}
          radius="lg"
          withBorder
        >
          {/* Header */}
          <Box
            style={{
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              borderTopLeftRadius: rem(12),
              borderTopRightRadius: rem(12),
              padding: rem(16),
            }}
          >
            <Group justify="space-between">
              <Group gap="xs">
                <ThemeIcon size="md" radius="xl" variant="white" color="grape">
                  <Brain size={18} />
                </ThemeIcon>
                <div>
                  <Text size="sm" fw={700} c="white">
                    AI Home Assistant
                  </Text>
                  <Text size="xs" c="rgba(255,255,255,0.8)">
                    Ask me anything about your home
                  </Text>
                </div>
              </Group>
              <Group gap="xs">
                {aiThinking && (
                  <Badge
                    size="sm"
                    variant="white"
                    color="grape"
                    leftSection={<Sparkles size={12} />}
                  >
                    Thinking...
                  </Badge>
                )}
                <ActionIcon
                  variant="subtle"
                  color="white"
                  onClick={toggleExpanded}
                  size="sm"
                >
                  {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </ActionIcon>
                <ActionIcon variant="subtle" color="white" onClick={onClose} size="sm">
                  <X size={16} />
                </ActionIcon>
              </Group>
            </Group>
          </Box>

          {/* Chat Messages */}
          <Box
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: rem(16),
              backgroundColor: 'var(--mantine-color-gray-0)',
            }}
          >
            {chatMessages.length === 0 ? (
              <Stack gap="md" align="center" justify="center" h="100%">
                <ThemeIcon size={60} radius="xl" variant="light" color="grape">
                  <Brain size={32} />
                </ThemeIcon>
                <Stack gap="xs" align="center">
                  <Text size="sm" fw={600} ta="center">
                    Welcome to your AI Home Assistant
                  </Text>
                  <Text size="xs" c="dimmed" ta="center" maw={300}>
                    I can help you understand your home's status, control devices, and answer
                    questions about your sensors and automation.
                  </Text>
                </Stack>
                <Stack gap="xs" mt="md" w="100%">
                  <Text size="xs" c="dimmed" fw={600}>
                    Try asking:
                  </Text>
                  <Paper
                    p="xs"
                    withBorder
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleExampleClick('Are any devices behaving erratically?')}
                  >
                    <Text size="xs">Are any devices behaving erratically?</Text>
                  </Paper>
                  <Paper
                    p="xs"
                    withBorder
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleExampleClick('What are the current anomaly scores?')}
                  >
                    <Text size="xs">What are the current anomaly scores?</Text>
                  </Paper>
                  <Paper
                    p="xs"
                    withBorder
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleExampleClick('Show me my comfort preferences')}
                  >
                    <Text size="xs">Show me my comfort preferences</Text>
                  </Paper>
                  <Paper
                    p="xs"
                    withBorder
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleExampleClick('How is the machine learning performing?')}
                  >
                    <Text size="xs">How is the machine learning performing?</Text>
                  </Paper>
                </Stack>
              </Stack>
            ) : (
              <Stack gap="md">
                {chatMessages.map((msg, idx) => (
                  <Paper
                    key={idx}
                    p="sm"
                    radius="md"
                    style={{
                      backgroundColor:
                        msg.role === 'user'
                          ? 'var(--mantine-color-grape-6)'
                          : 'white',
                      color: msg.role === 'user' ? 'white' : 'inherit',
                      alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                      maxWidth: '85%',
                      border: msg.role === 'assistant' ? '1px solid var(--mantine-color-gray-3)' : 'none',
                    }}
                  >
                    {msg.role === 'user' ? (
                      <Text size="sm">{msg.content}</Text>
                    ) : (
                      <Box
                        style={{
                          fontSize: 'var(--mantine-font-size-sm)',
                          lineHeight: 1.5,
                        }}
                      >
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => (
                              <Text size="sm" style={{ margin: '0 0 0.5em 0' }}>
                                {children}
                              </Text>
                            ),
                            strong: ({ children }) => (
                              <Text component="span" fw={700}>
                                {children}
                              </Text>
                            ),
                            li: ({ children }) => <li style={{ marginLeft: 8 }}>{children}</li>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </Box>
                    )}
                    {msg.action && (
                      <Badge size="xs" mt="xs" color="green" variant="light">
                        Action: {msg.action.command}
                      </Badge>
                    )}
                  </Paper>
                ))}
                <div ref={chatEndRef} />
              </Stack>
            )}
          </Box>

          {/* Input Area */}
          <Box
            style={{
              padding: rem(16),
              borderTop: '1px solid var(--mantine-color-gray-3)',
              backgroundColor: 'white',
            }}
          >
            <Group gap="xs" align="flex-end">
              <Textarea
                placeholder="Ask me anything..."
                value={chatInput}
                onChange={(e) => setChatInput(e.currentTarget.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleChatSubmit();
                  }
                }}
                autosize
                minRows={1}
                maxRows={4}
                style={{ flex: 1 }}
                styles={{
                  input: {
                    borderRadius: rem(12),
                  },
                }}
              />
              <Button
                onClick={handleChatSubmit}
                loading={chatLoading}
                leftSection={<Send size={16} />}
                radius="xl"
                variant="gradient"
                gradient={{ from: 'grape', to: 'violet' }}
              >
                Send
              </Button>
            </Group>
          </Box>
        </Paper>
      )}
    </Transition>
  );
}
