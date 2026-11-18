# 00 Security Foundations

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 1. Security foundations

Security should be designed into the application from the beginning. A
modern application has several connected attack surfaces:

-   Frontend and browser
-   Backend services and APIs
-   Authentication and authorization
-   Databases and file storage
-   Document ingestion and processing
-   Embedding and retrieval pipelines
-   Vector databases
-   LLM prompts, outputs, and tools
-   Cloud infrastructure, networks, and dependencies
-   People, operational processes, and third-party services

A weakness in one layer can undermine controls in another. For example,
a well-protected LLM cannot compensate for a backend endpoint that lets
one customer download another customer's documents.

### Core principles

1.  **Least privilege:** Give users, services, and AI agents only the
    permissions they need.
2.  **Defense in depth:** Use multiple independent safeguards rather
    than relying on one control.
3.  **Zero trust:** Authenticate and authorize each access; do not
    assume that an internal request is safe.
4.  **Secure defaults:** Deny access unless it is explicitly permitted.
5.  **Minimize data:** Collect, retain, expose, and send only the data
    required.
6.  **Assume input is untrusted:** This includes user input, uploaded
    files, retrieved documents, third-party API responses, and model
    output.
7.  **Make security observable:** Log important events, monitor for
    abuse, and prepare an incident response process.
8.  **Test continuously:** Reassess the application as code,
    dependencies, data, models, and infrastructure change.
