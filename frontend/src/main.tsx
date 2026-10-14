import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { App } from './App';
import { queryClient } from './query';
import { AuthProvider } from './auth';
import { DraftProvider } from './drafts';
import '@fontsource-variable/manrope';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('The application root is missing.');
const router = createBrowserRouter([{ path: '*', element: <AuthProvider><DraftProvider><App /></DraftProvider></AuthProvider> }]);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
