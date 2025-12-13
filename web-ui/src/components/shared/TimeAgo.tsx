import { Text } from '@mantine/core';
import { useEffect, useState } from 'react';

interface TimeAgoProps {
  timestamp: string | undefined;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  color?: string;
}

function formatTimeAgo(timestamp: string | undefined): string {
  if (!timestamp) return 'Never';

  const now = new Date().getTime();
  const updateTime = new Date(timestamp).getTime();
  const diffMs = now - updateTime;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 10) return 'Just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${diffDay}d ago`;
}

export function TimeAgo({ timestamp, size = 'xs', color = 'dimmed' }: TimeAgoProps) {
  const [timeAgo, setTimeAgo] = useState(() => formatTimeAgo(timestamp));

  useEffect(() => {
    // Update immediately
    setTimeAgo(formatTimeAgo(timestamp));

    // Update every 10 seconds
    const interval = setInterval(() => {
      setTimeAgo(formatTimeAgo(timestamp));
    }, 10000);

    return () => clearInterval(interval);
  }, [timestamp]);

  return (
    <Text size={size} c={color}>
      {timeAgo}
    </Text>
  );
}
