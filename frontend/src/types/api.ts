/** Types aligned with backend/app/api/schemas.py */

export interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  role?: string | null;
  is_active: boolean;
  is_locked: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export interface OverviewStats {
  total_requests: number;
  blocked_requests: number;
  active_incidents: number;
  open_approvals: number;
  current_risk: number;
  requests_24h: { hour: string; count: number }[];
  top_attacking_ips: { ip: string; requests: number; threats: number }[];
  top_risk_users: { actor_id: string; avg_risk: number; requests: number }[];
  attack_types: { attack_type: string; count: number }[];
  event_counts_by_type: { event_type: string; count: number }[];
  decisions_today: { decision: string; count: number }[];
}

export interface SecurityEvent {
  id: string;
  event_id: string;
  timestamp: string;
  event_type: string;
  severity: string;
  actor_id?: string | null;
  source_ip?: string | null;
  endpoint?: string | null;
  risk_score?: number | null;
  decision?: string | null;
  reasons?: string[] | null;
  details?: Record<string, unknown> | null;
  detection_source?: string | null;
  mitre_techniques?: string[] | null;
  incident_id?: string | null;
}

export interface Incident {
  id: string;
  incident_number: number;
  title: string;
  description?: string | null;
  severity: string;
  status: string;
  confidence: number;
  attack_type?: string | null;
  attacker_key?: string | null;
  timeline?: TimelineEntry[] | null;
  mitre_techniques?: string[] | null;
  related_event_ids?: string[] | null;
  first_seen: string;
  last_seen?: string | null;
}

export interface TimelineEntry {
  time: string;
  event_type: string;
  event_id: string;
  endpoint?: string | null;
}

export interface Policy {
  id: string;
  name: string;
  description?: string | null;
  enabled: boolean;
  priority: number;
  when: Record<string, unknown>;
  action: string;
  response_actions?: string[] | null;
  message?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ModelVersion {
  id: string;
  name: string;
  algorithm: string;
  version: number;
  status: string;
  metrics?: Record<string, unknown> | null;
  feature_names?: string[] | null;
  training_size: number;
  description?: string | null;
  trained_at?: string | null;
}

export interface Tool {
  id: string;
  name: string;
  description?: string | null;
  category: string;
  sensitive: boolean;
  requires_approval: boolean;
  enabled: boolean;
}

export interface Approval {
  id: string;
  invocation_id: string;
  actor_id?: string | null;
  tool_name: string;
  arguments?: Record<string, unknown> | null;
  risk_score?: number | null;
  reasons?: string[] | null;
  status: string;
  created_at: string;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  actor_id?: string | null;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  ip_address?: string | null;
  details?: Record<string, unknown> | null;
  status: string;
}

export interface LiveThreat {
  event_id: string;
  timestamp: string;
  event_type: string;
  severity: string;
  actor_id?: string | null;
  source_ip?: string | null;
  endpoint?: string | null;
  risk_score?: number | null;
  decision?: string | null;
  reasons?: string[] | null;
  mitre_techniques?: string[] | null;
  incident_id?: string | null;
}

export interface RequestTimeseries {
  hour: string;
  count: number;
  blocked: number;
  avg_risk: number;
}
