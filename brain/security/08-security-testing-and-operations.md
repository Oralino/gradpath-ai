# 08 Security Testing And Operations

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 10. Security testing and operational practices

### 10.1 Threat modeling

Before implementation or a major change, ask:

1.  What assets are valuable?
2.  Who are the users, administrators, service accounts, and potential
    attackers?
3.  What are the entry points and trust boundaries?
4.  What can go wrong at each boundary?
5.  What is the likelihood and impact of each threat?
6.  Which controls prevent or detect it?
7.  How will the controls be tested?
8.  What is the recovery plan if prevention fails?

Useful methods include STRIDE (Spoofing, Tampering, Repudiation,
Information Disclosure, Denial of Service, Elevation of Privilege) and
data-flow diagrams.

### 10.2 Security testing checklist

-   [ ] Review authentication and account recovery.
-   [ ] Test authorization with multiple users and roles.
-   [ ] Test tenant isolation for every document and retrieval path.
-   [ ] Review file upload and document parsing.
-   [ ] Review database queries and input handling.
-   [ ] Check API schemas, permissions, and rate limits.
-   [ ] Review CORS, cookies, TLS, and security headers.
-   [ ] Scan dependencies and container images.
-   [ ] Review secrets and repository history.
-   [ ] Test prompt injection in user input and retrieved documents.
-   [ ] Test whether private content can cross user or tenant
    boundaries.
-   [ ] Validate model outputs and tool arguments.
-   [ ] Review logging for sensitive-data leakage.
-   [ ] Test backup restoration and incident procedures.

Perform security testing only on systems you own or have explicit
permission to assess. Use isolated test data and environments.

### 10.3 Logging and monitoring

Log security-relevant events such as: - Authentication successes and
failures. - Permission denials. - Sensitive document access and
downloads. - Administrative changes. - Document ingestion, deletion, and
re-indexing. - Unusual API usage and rate-limit events. - AI tool calls
and approval outcomes. - Unexpected cost or token consumption.

Logging safeguards: - Never log passwords, API keys, session tokens, or
unnecessary sensitive content. - Restrict log access and protect log
integrity. - Set retention periods. - Alert on meaningful anomalies. -
Correlate events using request IDs while minimizing personal data.

### 10.4 Incident response

Prepare a written process for: 1. Detecting and reporting an incident.
2. Assessing scope and affected systems or data. 3. Containing access or
compromised services. 4. Preserving relevant evidence. 5. Removing the
cause and restoring securely. 6. Notifying affected parties and
authorities where legally required. 7. Reviewing lessons learned and
improving controls.
