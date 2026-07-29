export type ConnectorStatus = 'disconnected' | 'connected';

export const CONNECTOR_STATUS_STORAGE_KEY = 'halil.connectorStatuses';

function readStatuses(): Record<string, ConnectorStatus> {
  try {
    const raw = sessionStorage.getItem(CONNECTOR_STATUS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, ConnectorStatus>) : {};
  } catch {
    return {};
  }
}

/**
 * Marks a connector as connected in the shared session-storage-backed status
 * map. Used by each connector's own setup flow (Jira project selection,
 * Google Drive folder setup, etc.) once the user finishes that flow, so the
 * connector card only shows "연결됨" after the final step is completed.
 */
export function markConnectorConnected(id: string) {
  try {
    const current = readStatuses();
    current[id] = 'connected';
    sessionStorage.setItem(CONNECTOR_STATUS_STORAGE_KEY, JSON.stringify(current));
  } catch {
    // ignore storage failures (e.g. private browsing)
  }
}
