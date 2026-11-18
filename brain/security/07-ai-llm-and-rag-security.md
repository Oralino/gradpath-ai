# 07 Ai Llm And Rag Security

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 8. AI, LLM, and RAG-specific threats

RAG systems add risk because they combine user instructions, retrieved
content, model-generated output, and sometimes tools that can take
actions. The model should never be treated as the security boundary.
Enforce security in ordinary application code and infrastructure.

### 8.1 Direct prompt injection

**What it is:** A user crafts input intended to override or manipulate
the model's intended task or behavior.

**Potential impact:** Policy evasion, misleading responses, attempts to
expose context, or attempts to trigger unauthorized tool use.

**Defenses:** - Treat user input as untrusted. - Keep system
instructions separate from user content. - Use clear task boundaries and
constrained workflows. - Do not put secrets in prompts. - Enforce
authorization outside the model. - Restrict tools and validate every
tool request. - Test with adversarial prompts as part of an authorized
evaluation. - Do not assume a stronger system prompt solves prompt
injection.

### 8.2 Indirect prompt injection

**What it is:** Malicious instructions are placed in content the model
later reads, such as PDFs, web pages, emails, tickets, or retrieved
documents.

**Potential impact:** The model may follow untrusted content as if it
were an instruction.

**Defenses:** - Treat retrieved content as data, never as trusted
instructions. - Clearly delimit and label retrieved content. - Restrict
the model's tools and permissions. - Require independent authorization
checks before actions. - Review and track content sources. - Use human
approval for consequential actions. - Test ingestion and retrieval using
controlled adversarial documents.

**Important:** Prompt injection cannot be reliably eliminated by prompt
wording alone. Architectural controls are essential.

### 8.3 RAG and knowledge-base poisoning

**What it is:** Untrusted, misleading, or malicious documents are added
to the knowledge base to influence retrieval and answers.

**Defenses:** - Restrict who can upload or modify documents. -
Authenticate ingestion sources. - Track provenance, uploader, tenant,
timestamps, and versions. - Validate file type and content. - Review
high-impact sources before publication. - Separate trusted, reviewed,
and unreviewed collections. - Support document quarantine, rollback, and
deletion. - Monitor unusual ingestion patterns and retrieval outcomes.

### 8.4 Sensitive information disclosure through the LLM

**What it is:** The model reveals private documents, conversation
context, personal information, credentials, or internal data.

**Defenses:** - Enforce authorization before retrieval and before every
tool action. - Apply tenant and user filters server-side. - Minimize
sensitive context sent to the model. - Redact secrets and unnecessary
personal data. - Do not rely on the model to decide whether a user is
authorized. - Test with separate users, roles, and tenants. - Avoid
logging sensitive prompts and responses unnecessarily.

### 8.5 Cross-tenant retrieval leakage

**What it is:** A user receives documents belonging to another customer
or tenant because retrieval is not correctly scoped.

**Defenses:** - Apply tenant restrictions in the trusted backend
retrieval layer. - Derive tenant identity from the authenticated
session, not user-supplied metadata. - Enforce ownership and
authorization on every retrieved chunk and parent document. - Re-check
permissions when documents are updated or access is revoked. - Test
isolation with multiple tenants and adversarial identifiers. - Consider
separate collections or indexes for stronger isolation where
justified. - Ensure caches also respect tenant and user boundaries.

### 8.6 Vector database attacks

**Threats include:** - Unauthorized reads, writes, or deletions. - Weak
database credentials. - Incorrect metadata filters. - Cross-tenant
search. - Exposure of sensitive source text or metadata. - Malicious or
misleading records.

**Defenses:** - Keep vector databases off the public internet unless
strictly required. - Use authentication, network restrictions, and
least-privilege credentials. - Apply server-side tenant and
authorization filters. - Validate metadata and ingestion records. -
Encrypt connections and storage where supported. - Audit access and
administrative changes. - Back up indexes and test recovery. - Remember
that embeddings and metadata may still reveal sensitive information.

### 8.7 Excessive agency and unsafe tool use

**What it is:** An AI agent has more access or autonomy than its task
requires, allowing manipulation to cause unintended actions.

**Potential impact:** Unauthorized file access, data changes, messages,
API operations, or other consequential actions.

**Defenses:** - Give each agent only the minimum tools and permissions
required. - Separate read-only and write-capable tools. - Enforce
authorization in the tool implementation, not in the prompt. - Validate
tool arguments against strict schemas. - Allowlist destinations and
operations. - Require human approval for sensitive or irreversible
actions. - Use transaction limits, idempotency, and rollback where
appropriate. - Log tool calls and their outcomes. - Use isolated
execution environments for any necessary code execution.

### 8.8 Insecure output handling

**What it is:** Model output is trusted and passed into another system
without validation or safe encoding.

**Potential impact:** XSS, unsafe database operations, malformed
downstream requests, or unintended actions.

**Defenses:** - Treat model output as untrusted input. - Validate
structured output against strict schemas. - Escape output for its
destination context. - Use parameterized queries. - Do not execute
generated code or commands directly. - Validate URLs and tool
arguments. - Apply authorization independently of model output.

### 8.9 Unbounded consumption and model denial of service

**What it is:** Excessive or unusually expensive requests consume model
tokens, compute, storage, or paid API quota.

**Defenses:** - Apply per-user and per-tenant quotas. - Limit prompt,
document, and response sizes. - Limit tokens, concurrency, and
processing time. - Rate-limit expensive endpoints. - Cache safe,
appropriate results. - Monitor cost and usage anomalies. - Set provider
budgets and alerts. - Protect ingestion pipelines from oversized or
highly complex files.

### 8.10 System prompt leakage

**What it is:** Internal prompt instructions are exposed through model
responses or application behavior.

**Defenses:** - Do not store passwords, keys, or confidential data in
prompts. - Assume prompt text may be disclosed. - Keep access control
and business rules in backend code. - Limit internal implementation
details in prompts. - Treat prompt confidentiality as defense-in-depth,
not a security boundary.

### 8.11 Model and AI supply-chain attacks

**What they are:** A model, adapter, dataset, package, plugin, or
external AI service is compromised or untrustworthy.

**Defenses:** - Obtain models and packages from trusted sources. -
Verify provenance and checksums where available. - Review licenses and
model capabilities. - Scan and isolate model-loading and conversion
workflows. - Pin versions and track changes. - Evaluate third-party
services and their data-handling policies. - Keep a record of model,
prompt, and dependency versions.

### 8.12 Model theft and extraction

**What it is:** Unauthorized access to proprietary model assets or
repeated querying intended to reproduce model behavior.

**Defenses:** - Protect model files and inference endpoints. -
Authenticate clients and apply quotas. - Monitor unusual query
patterns. - Restrict access to model storage and deployment
infrastructure. - Avoid exposing unnecessary internal metadata.

### 8.13 Model poisoning and fine-tuning risks

**What they are:** Training or fine-tuning data is manipulated, causing
unwanted behavior or degraded reliability.

**Defenses:** - Establish trusted dataset sources and provenance. -
Review and deduplicate training data. - Version datasets and model
artifacts. - Evaluate models before deployment and after updates. - Keep
a rollback path. - Separate data preparation permissions from deployment
permissions.

### 8.14 Hallucination and misinformation

**What it is:** The model generates unsupported or incorrect
information, potentially presenting it confidently.

**Defenses:** - Require evidence and citations for knowledge-grounded
answers. - Show source documents where appropriate. - Evaluate answer
faithfulness and retrieval quality. - Communicate uncertainty. - Use
human review for high-impact decisions. - Do not use an LLM as the sole
authority for security, legal, financial, or safety-critical decisions.

---

## 9. RAG architecture: security controls by stage

### 9.1 User and frontend layer

Risks: - XSS and CSRF. - Credential theft and session misuse. -
Oversized or malicious uploads. - Unauthorized access hidden by
frontend-only checks.

Controls: - Secure authentication and session settings. - Output
encoding and CSRF protection. - Upload limits and server-side
validation. - No secrets in frontend code. - Treat the frontend as
untrusted; enforce all permissions on the backend.

### 9.2 Backend and API layer

Risks: - SQL injection. - IDOR/BOLA and privilege escalation. - SSRF. -
Missing rate limits. - Excessive data exposure.

Controls: - Parameterized queries. - Centralized authorization checks. -
Strict request and response schemas. - Outbound network restrictions. -
Rate limits, quotas, and timeouts. - Safe error handling.

### 9.3 Document ingestion and embedding layer

Risks: - Malicious files and parser vulnerabilities. - Document
poisoning. - Prompt injection embedded in documents. - Cross-tenant
ingestion mistakes. - Resource exhaustion from large or complex files.

Controls: - Restrict upload permissions. - Validate file signatures,
sizes, and formats. - Process files in isolated environments. - Track
document provenance and ownership. - Apply tenant boundaries before
indexing. - Quarantine, review, version, and remove documents. - Set
processing limits.

### 9.4 Vector database and retrieval layer

Risks: - Unauthorized access to vectors and metadata. - Cross-tenant
retrieval. - Incorrect or missing metadata filters. - Stale permissions
after access changes. - Sensitive information exposed in chunks.

Controls: - Private network access and least-privilege credentials. -
Server-side authorization filters. - Verify each result against current
access rights. - Keep metadata trustworthy and validated. - Avoid
storing unnecessary sensitive information. - Audit access and test
tenant isolation.

### 9.5 Prompt construction and model layer

Risks: - Direct and indirect prompt injection. - Sensitive context
disclosure. - Untrusted retrieved text treated as instructions. -
Excessive context and token consumption.

Controls: - Separate trusted instructions from untrusted content. -
Label and delimit retrieved passages. - Minimize context and redact
secrets. - Apply authorization before context is assembled. - Use
constrained output formats where useful. - Do not rely on prompts for
access control.

### 9.6 Response and tool layer

Risks: - Unsafe HTML or structured output. - Unauthorized tool
actions. - Excessive agent permissions. - Unvalidated URLs, SQL, or
command-like content.

Controls: - Validate outputs and tool arguments. - Escape content for
the output context. - Enforce permissions inside each tool. - Use
least-privilege tools and human approval for sensitive actions. - Log
actions and support rollback where possible.
