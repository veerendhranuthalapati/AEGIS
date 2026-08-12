## Summary

<!-- What changed and why -->

## Security impact

<!-- Authentication, authorization, detection rules, policies, secrets, logging, upstream behavior -->

## Tests

<!-- Commands run and results -->

## Attack scenarios

<!-- Relevant attack-lab / bypass cases, or N/A -->

## Infrastructure impact

<!-- Docker, Terraform, CI — or N/A -->

## Breaking changes

<!-- API, policy, deployment — or none -->

## Checklist

- [ ] Backend pytest passes
- [ ] Ruff and mypy pass (if Python changed)
- [ ] Frontend tests and build pass (if UI changed)
- [ ] Attack lab (`attack_lab/scripts/run_all.py`) verified when security behavior changed
- [ ] Bypass suite verified when encoding/normalization changed
- [ ] No secrets, `.env`, databases, models, or build artifacts committed
- [ ] Documentation updated when behavior or limitations changed
