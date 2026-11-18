# 09 Rag Application Security Checklist

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 11. Practical security checklist for a new RAG application

### Identity and access

-   [ ] Use a reputable authentication library or provider.
-   [ ] Support MFA or passkeys where appropriate.
-   [ ] Enforce authorization on every backend endpoint.
-   [ ] Check user, tenant, document, and action permissions.
-   [ ] Revoke access promptly when permissions change.

### Backend and APIs

-   [ ] Validate all input against explicit schemas.
-   [ ] Use parameterized database queries.
-   [ ] Configure CORS deliberately.
-   [ ] Protect state-changing browser requests against CSRF.
-   [ ] Apply rate limits, timeouts, and request-size limits.
-   [ ] Avoid exposing stack traces and internal details.

### Data and databases

-   [ ] Keep database credentials out of frontend code.
-   [ ] Use least-privilege service accounts.
-   [ ] Encrypt data in transit and at rest where appropriate.
-   [ ] Restrict database network access.
-   [ ] Protect and test backups.
-   [ ] Minimize retention of sensitive data.

### RAG and AI

-   [ ] Treat user input and retrieved documents as untrusted.
-   [ ] Track document source, owner, tenant, and version.
-   [ ] Enforce access control before retrieval.
-   [ ] Test cross-tenant isolation.
-   [ ] Keep secrets out of prompts and context.
-   [ ] Validate model outputs and structured responses.
-   [ ] Restrict tools and require approval for consequential actions.
-   [ ] Set token, concurrency, and cost limits.

### Deployment and operations

-   [ ] Store secrets in a secrets manager or protected environment
    configuration.
-   [ ] Never commit secrets to source control.
-   [ ] Use HTTPS.
-   [ ] Keep dependencies and base images updated.
-   [ ] Scan code and dependencies.
-   [ ] Separate development, staging, and production.
-   [ ] Monitor important security events.
-   [ ] Maintain and test an incident response plan.
