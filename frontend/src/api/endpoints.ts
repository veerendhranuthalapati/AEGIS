import { api } from "./client";
import type {
  Approval,
  AuditLog,
  Incident,
  LiveThreat,
  LoginResponse,
  ModelVersion,
  OverviewStats,
  Policy,
  RequestTimeseries,
  SecurityEvent,
  Tool,
  User,
} from "@/types/api";

export const authApi = {
  login: (username: string, password: string) =>
    api.post<LoginResponse>("/api/auth/login", { username, password }).then((r) => r.data),
  me: () => api.get<User>("/api/auth/me").then((r) => r.data),
  logout: () => api.post("/api/auth/logout").then((r) => r.data),
};

export const analyticsApi = {
  overview: () => api.get<OverviewStats>("/api/analytics/overview").then((r) => r.data),
  requests: (hours = 24) =>
    api.get<RequestTimeseries[]>("/api/analytics/requests", { params: { hours } }).then((r) => r.data),
  attackTimeline: (limit = 50) =>
    api.get("/api/analytics/attack-timeline", { params: { limit } }).then((r) => r.data),
};

export const incidentsApi = {
  list: () => api.get<Incident[]>("/api/incidents").then((r) => r.data),
  get: (id: string) => api.get<Incident>(`/api/incidents/${id}`).then((r) => r.data),
  update: (id: string, body: { status?: string; severity?: string }) =>
    api.patch<Incident>(`/api/incidents/${id}`, body).then((r) => r.data),
};

export const eventsApi = {
  list: (params?: { event_type?: string; severity?: string; limit?: number }) =>
    api.get<SecurityEvent[]>("/api/events", { params }).then((r) => r.data),
  summary: () => api.get("/api/events/summary").then((r) => r.data),
};

export const threatsApi = {
  live: (minutes = 60, limit = 50) =>
    api.get<LiveThreat[]>("/api/threats/live", { params: { minutes, limit } }).then((r) => r.data),
  blockedIps: () => api.get("/api/threats/blocked-ips").then((r) => r.data),
};

export const policiesApi = {
  list: () => api.get<Policy[]>("/api/policies").then((r) => r.data),
  create: (body: Partial<Policy>) => api.post<Policy>("/api/policies", body).then((r) => r.data),
  update: (id: string, body: Partial<Policy>) =>
    api.patch<Policy>(`/api/policies/${id}`, body).then((r) => r.data),
  delete: (id: string) => api.delete(`/api/policies/${id}`).then((r) => r.data),
};

export const mlApi = {
  models: () => api.get<ModelVersion[]>("/api/ml/models").then((r) => r.data),
  latest: () => api.get<ModelVersion | null>("/api/ml/models/latest").then((r) => r.data),
  train: (size = 1500, seed = 42) =>
    api.post("/api/ml/train", { size, seed }).then((r) => r.data),
};

export const toolsApi = {
  list: () => api.get<Tool[]>("/api/tools").then((r) => r.data),
  approvals: () => api.get<Approval[]>("/api/tools/approvals").then((r) => r.data),
  decideApproval: (id: string, approve: boolean) =>
    api.post(`/api/tools/approvals/${id}/decide`, { approve }).then((r) => r.data),
};

export const usersApi = {
  list: () => api.get<User[]>("/api/users").then((r) => r.data),
};

export const auditApi = {
  list: (params?: { limit?: number; action?: string; actor_id?: string }) =>
    api.get<AuditLog[]>("/api/audit", { params }).then((r) => r.data),
};

export const healthApi = {
  check: () => api.get<{ status: string }>("/health").then((r) => r.data),
};
