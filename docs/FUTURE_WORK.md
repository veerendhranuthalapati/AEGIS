# AEGIS Future Work

Ranked by value. Each item addresses a documented limitation in [LIMITATIONS.md](LIMITATIONS.md) — not speculative feature creep.

---

## HIGH VALUE

### 1. Real cybersecurity dataset for ML

**Problem:** Synthetic training data produces misleading accuracy metrics.  
**Direction:** Train/evaluate on public API security datasets (e.g., HTTP request logs with labeled attacks) or anonymized production-like traces.  
**Outcome:** Defensible precision/recall claims and calibrated thresholds.

### 2. Real LLM provider integration

**Problem:** LLM tier tested against mock echo upstream only.  
**Direction:** Optional OpenAI-compatible provider with secret injection, timeout/fallback to deterministic rules (already partially supported in settings).  
**Outcome:** Validate prompt scanner and cost controls against real model behavior.

### 3. Real cloud deployment

**Problem:** Terraform is defined but not applied; secrets/ECR/ACM are placeholders.  
**Direction:** Staged apply in non-prod AWS account, populate Secrets Manager, run migrations, load test on ECS.  
**Outcome:** Prove operational runbooks in [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md).

### 4. Distributed rate limiting

**Problem:** Rate counters in PostgreSQL do not scale horizontally across gateway replicas.  
**Direction:** Redis/ElastiCache sliding windows with same semantics as current login/gateway limits.  
**Outcome:** Consistent throttling under multi-task ECS.

### 5. Stronger behavioral modeling

**Problem:** Behavioral signals are aggregate SQL counts — high latency (~110 ms) and limited context.  
**Direction:** Materialized views, incremental rollups, or stream processing for stats; session/device graphs.  
**Outcome:** Lower latency and richer anomaly features.

### 6. Adversarial ML evaluation

**Problem:** No systematic evasion testing against the feature vector.  
**Direction:** FGSM-style perturbations on numeric features, rule+ML bypass fuzzing, retrain loop.  
**Outcome:** Understand false negative surface before any production ML claim.

---

## MEDIUM VALUE

### 7. More agent / tool integrations

**Problem:** Tool registry covers demo tools only.  
**Direction:** OpenAPI-driven tool registration, MCP adapter, per-tool policy templates.  
**Outcome:** Broader agent-security demonstrations.

### 8. Richer incident graph

**Problem:** Correlation engine groups by time/actor/key — flat incident model.  
**Direction:** Entity graph (IP, user, endpoint, tool), attack-chain linking, STIX export.  
**Outcome:** Better SOC analyst workflow in frontend.

### 9. Automated response integrations

**Problem:** BLOCK/REQUIRE_REVIEW stops at HTTP response.  
**Direction:** Webhook to SIEM, Slack PagerDuty, optional WAF IP block list (with human approval).  
**Outcome:** Close loop from detection to response — still fail-safe on gateway.

### 10. Expanded compliance mappings

**Problem:** MITRE techniques partially tagged.  
**Direction:** Map findings to OWASP API Top 10, NIST CSF, ISO 27001 control IDs in incident export.  
**Outcome:** Easier enterprise conversations — documentation only until validated.

---

## Explicitly out of scope (feature freeze)

Unless a **security or correctness bug** is found:

- New microservices split
- Additional ML model families “for demo”
- New LLM providers without integration plan
- Frontend redesign
- Random dashboard widgets

See [PROJECT_COMPLETION_REPORT.md](verification/PROJECT_COMPLETION_REPORT.md).
