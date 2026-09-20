/** Derived values ported verbatim from v1 ui/tab_bug_report.py. */

export const DEVICE_TYPES = ['Not specified', 'Desktop', 'Mobile', 'Tablet'] as const;

export type DeviceType = (typeof DEVICE_TYPES)[number];

export function computeReproducibility(totalAttempts: number, successfulAttempts: number): string {
  if (successfulAttempts === 0) return 'Always';
  if (successfulAttempts < totalAttempts)
    return `Intermittent (${successfulAttempts} of ${totalAttempts})`;
  return '';
}

export type EnvironmentParts = {
  device_type: DeviceType;
  os_version?: string;
  browser_version?: string;
  build_env?: string;
  bug_url?: string;
};

export function buildEnvironmentString(parts: EnvironmentParts): string {
  const envParts: string[] = [];
  if (parts.device_type !== 'Not specified') envParts.push(`Device: ${parts.device_type}`);
  if (parts.os_version?.trim()) envParts.push(`OS: ${parts.os_version.trim()}`);
  if (parts.browser_version?.trim()) envParts.push(`Browser/App: ${parts.browser_version.trim()}`);
  if (parts.build_env?.trim()) envParts.push(`Build/Env: ${parts.build_env.trim()}`);
  if (parts.bug_url?.trim()) envParts.push(`URL: ${parts.bug_url.trim()}`);
  return envParts.length > 0 ? envParts.join('; ') : 'Not provided';
}
