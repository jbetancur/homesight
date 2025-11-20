import React, { useEffect, useRef } from 'react';
import { EventContext } from './eventContext';
import type { EventCallback } from './eventContext';

export const EventProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const callbacksRef = useRef<EventCallback[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const connect = () => {
      console.log('🔌 Establishing SSE connection...');
      const es = new window.EventSource('http://localhost:8080/api/events');
      eventSourceRef.current = es;

      es.onopen = () => {
        console.log('✅ SSE connection established');
      };

      es.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          console.log('📨 SSE event received:', msg.type);
          callbacksRef.current.forEach(cb => cb(msg));
        } catch (err) {
          console.error('Failed to parse SSE message:', err);
        }
      };

      es.onerror = () => {
        console.log('❌ SSE connection lost, reconnecting in 3s...');
        es.close();
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      };
    };

    connect();

    return () => {
      console.log('🔌 Cleaning up SSE connection');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      eventSourceRef.current?.close();
    };
  }, []);

  const subscribe = (cb: EventCallback) => {
    callbacksRef.current.push(cb);
    return () => {
      callbacksRef.current = callbacksRef.current.filter(fn => fn !== cb);
    };
  };

  return <EventContext.Provider value={{ subscribe }}>{children}</EventContext.Provider>;
};

