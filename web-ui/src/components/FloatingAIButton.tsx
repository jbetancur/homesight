import { ActionIcon, Tooltip } from '@mantine/core';
import { Brain } from 'lucide-react';

interface FloatingAIButtonProps {
  onClick: () => void;
}

export default function FloatingAIButton({ onClick }: FloatingAIButtonProps) {
  return (
    <Tooltip label="AI Home Assistant" position="left" withArrow>
      <ActionIcon
        size={60}
        radius="xl"
        variant="gradient"
        gradient={{ from: 'grape', to: 'violet', deg: 135 }}
        style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          zIndex: 999,
          boxShadow: '0 4px 20px rgba(103, 58, 183, 0.4)',
          transition: 'all 0.3s ease',
        }}
        onClick={onClick}
        styles={{
          root: {
            '&:hover': {
              transform: 'scale(1.1)',
              boxShadow: '0 6px 30px rgba(103, 58, 183, 0.6)',
            },
          },
        }}
      >
        <Brain size={28} />
      </ActionIcon>
    </Tooltip>
  );
}
