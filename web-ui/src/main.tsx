

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import './index.css';
import App from './App.tsx';
import { EventProvider } from './events';
import { AlertsProvider } from './context/AlertsContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider>
      <EventProvider>
        <AlertsProvider>
          <App />
        </AlertsProvider>
      </EventProvider>
    </MantineProvider>
  </StrictMode>
);
