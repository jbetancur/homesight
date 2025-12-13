import { Box } from '@mantine/core';
import type { CSSProperties } from 'react';

interface PulseIndicatorProps {
  active: boolean;
  color?: string;
  size?: number;
  children?: React.ReactNode;
}

export function PulseIndicator({ active, color = 'blue', size = 8, children }: PulseIndicatorProps) {
  if (!active && !children) return null;

  const pulseStyle: CSSProperties = active
    ? {
        position: 'relative',
        animation: 'pulse-glow 2s ease-in-out infinite',
      }
    : {};

  return (
    <>
      <style>
        {`
          @keyframes pulse-glow {
            0%, 100% {
              box-shadow: 0 0 0 0 var(--mantine-color-${color}-5);
              opacity: 1;
            }
            50% {
              box-shadow: 0 0 15px 5px var(--mantine-color-${color}-3);
              opacity: 0.8;
            }
          }
        `}
      </style>
      <Box style={pulseStyle}>
        {children || (
          <Box
            style={{
              width: size,
              height: size,
              borderRadius: '50%',
              backgroundColor: `var(--mantine-color-${color}-5)`,
            }}
          />
        )}
      </Box>
    </>
  );
}
