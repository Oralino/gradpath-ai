# 10 Learning Resources And Roadmap

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 12. Recommended learning resources

These are established resources for learning defensive application and
AI security:

-   [OWASP Top 10](https://top10.owasp.org/) --- common web application
    security risks.
-   [OWASP API Security
    Project](https://owasp.org/www-project-api-security/) --- API
    security risks.
-   [OWASP Top 10 for LLM
    Applications](https://genai.owasp.org/llm-top-10/) --- risks
    affecting LLM applications.
-   [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/) ---
    practical implementation guidance.
-   [PortSwigger Web Security
    Academy](https://portswigger.net/web-security) --- interactive web
    security education.
-   [OWASP ZAP](https://www.zaproxy.org/) --- open-source web
    application security testing.
-   [Semgrep](https://semgrep.dev/) --- static analysis and code
    security checks.
-   [Snyk](https://snyk.io/) --- dependency and developer security
    tooling.

---

## 13. Suggested learning order

1.  Networking and HTTP fundamentals: DNS, TCP/IP, TLS, cookies,
    headers, and proxies.
2.  Web application security: SQL injection, XSS, CSRF, SSRF, file
    handling, and path traversal.
3.  Authentication and authorization: sessions, OAuth, JWT, RBAC, IDOR,
    and BOLA.
4.  API security: validation, access control, rate limiting, and safe
    error handling.
5.  Data and infrastructure security: encryption, secrets, cloud
    permissions, backups, and supply chain.
6.  AI and RAG security: prompt injection, poisoned knowledge bases,
    retrieval isolation, output handling, and tool permissions.
7.  Security operations: threat modeling, testing, monitoring, incident
    response, and recovery.

---

## 14. Key takeaway

The most important RAG security rule is:

**The LLM is not the security boundary.**

Authentication, authorization, tenant isolation, data validation, tool
permissions, and network restrictions must be enforced by trusted
application code and infrastructure. Treat prompts, retrieved documents,
user input, third-party responses, and model output as untrusted. Use
layered controls, test the boundaries, monitor the system, and prepare
to recover when something goes wrong.
