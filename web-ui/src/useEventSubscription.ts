import { useContext, useEffect } from 'react';
import type { EventCallback } from './eventContext';
import { EventContext } from './eventContext';

export function useEventSubscription(cb: EventCallback) {
  const context = useContext(EventContext);
  useEffect(() => {
    if (!context) return;
    const unsubscribe = context.subscribe(cb);
    return unsubscribe;
  }, [context, cb]);
}
