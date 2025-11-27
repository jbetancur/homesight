/**
 * API Configuration for HomeSight Frontend
 *
 * AUTO-DETECTS backend URL based on current page location.
 * Works everywhere: localhost, same network, different ports, etc.
 */

function getAPIBase(): string {
  // 1. Check if VITE_API_BASE is set in environment (explicit override)
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }

  // 2. Check if window.__API_BASE__ is set (can be injected by server)
  if (typeof window !== 'undefined' && (window as any).__API_BASE__) {
    return (window as any).__API_BASE__;
  }

  // 3. Auto-detect: Use the same host as the frontend, but port 8080 for backend
  // This works for: localhost, remote IPs, docker hosts, everything!
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;

    // Get the port - if it's a dev server port, use 8080 for backend
    const currentPort = parseInt(window.location.port, 10);
    const isDevServerPort = [3000, 5173, 5174, 8000].includes(currentPort);

    // Use 8080 as backend port (where the API actually runs)
    const backendPort = isDevServerPort ? 8080 : currentPort;

    // Construct the backend URL using current protocol and hostname
    const protocol = window.location.protocol; // http: or https:
    const apiBase = `${protocol}//${hostname}:${backendPort}`;

    return apiBase;
  }

  // 4. Fallback
  return 'http://localhost:8080';
}

export const API_BASE = getAPIBase();
export const API_BASE_WITH_PATHS = `${API_BASE}/api`;

/**
 * How it works:
 *
 * This auto-detects the backend URL based on where the frontend is running.
 *
 * Examples:
 *   Frontend on 10.0.20.175:5173 → API calls go to http://10.0.20.175:8080/api
 *   Frontend on localhost:3000 → API calls go to http://localhost:8080/api
 *   Frontend on example.com:443 → API calls go to https://example.com:443/api
 *
 * The assumption: Backend always runs on :8080 (or same port as frontend in production)
 *
 * Override if needed:
 *   - Set VITE_API_BASE=http://custom-server:8080 before running npm
 *   - Or inject at runtime: window.__API_BASE__ = 'http://your-server:8080'
 */
