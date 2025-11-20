import { createContext } from 'react';

export type EventMessage = {
  type: string;
  data: any;
};

export type EventCallback = (event: EventMessage) => void;

export const EventContext = createContext<{ subscribe: (cb: EventCallback) => () => void } | null>(null);
