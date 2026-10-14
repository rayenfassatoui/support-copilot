import { QueryClient } from '@tanstack/react-query';
import type { TicketFilters } from './types';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 30_000 },
    mutations: { retry: false },
  },
});

export const queryKeys = {
  agents: ['agents'] as const,
  ticketLists: ['tickets', 'list'] as const,
  tickets: (filters: TicketFilters) => ['tickets', 'list', filters] as const,
  ticket: (id: string) => ['tickets', 'detail', id] as const,
  events: (id: string) => ['ticket-events', id] as const,
  messages: (id: string) => ['ticket-messages', id] as const,
  knowledge: ['knowledge', 'list'] as const,
  document: (id: string) => ['knowledge', 'document', id] as const,
};

export async function invalidateTicket(client: QueryClient, id: string): Promise<void> {
  await Promise.all([
    client.invalidateQueries({ queryKey: queryKeys.ticket(id) }),
    client.invalidateQueries({ queryKey: queryKeys.ticketLists }),
    client.invalidateQueries({ queryKey: queryKeys.events(id) }),
    client.invalidateQueries({ queryKey: queryKeys.messages(id) }),
  ]);
}
