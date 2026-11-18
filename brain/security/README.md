# Cybersecurity Reference for Web Apps and RAG

A collection of focused Markdown guides covering defensive cybersecurity for web applications, APIs, infrastructure, databases, and AI/RAG systems.

## Files

| File | Coverage |
|---|---|
| `00-security-foundations.md` | Security principles and attack surfaces |
| `01-web-application-security.md` | SQL injection, XSS, CSRF, SSRF, file uploads, path traversal, RCE, and misconfiguration |
| `02-authentication-and-access-control.md` | Brute force, credential stuffing, sessions, IDOR/BOLA, and privilege escalation |
| `03-api-security.md` | API authorization, excessive exposure, mass assignment, resource limits, and inventory |
| `04-network-and-infrastructure-security.md` | DDoS, MITM, DNS/IP spoofing, exposed services, and supply-chain compromise |
| `05-database-and-data-security.md` | Data breaches, exfiltration, tampering, poisoning, backups, and cryptography |
| `06-human-and-organizational-threats.md` | Phishing, social engineering, insider threats, and ransomware |
| `07-ai-llm-and-rag-security.md` | Prompt injection, RAG poisoning, vector database security, data leakage, agent/tool risks, and architecture controls |
| `08-security-testing-and-operations.md` | Threat modeling, security testing, logging, monitoring, and incident response |
| `09-rag-application-security-checklist.md` | Practical build-time security checklist |
| `10-learning-resources-and-roadmap.md` | Recommended references and learning sequence |

## How to use this folder

- Read `00-security-foundations.md` first.
- Use the topic-specific guides while designing each part of your application.
- Treat the checklists as starting points, not a guarantee of security.
- Revisit the documents as your architecture, dependencies, and threat model change.

## Important principle

**The LLM is not the security boundary.** Enforce authentication, authorization, tenant isolation, validation, tool permissions, and network restrictions in trusted application code and infrastructure.

These documents are defensive guidance. Test only systems you own or are explicitly authorized to assess.
