# 01 Web Application Security

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 2. Web application threats

### 2.1 SQL injection (SQLi)

**What it is:** Untrusted input changes the meaning of a database query.

**Potential impact:** Unauthorized data access or modification,
authentication bypass, and in severe cases damage to the database.

**Defenses:** - Use parameterized queries or prepared statements. - Use
safe ORM query interfaces correctly. - Avoid building SQL by
concatenating user input. - Give database accounts only the permissions
they require. - Validate input according to the expected type, length,
and format. - Return generic errors to users; keep diagnostic detail in
protected logs. - Test database-facing features with authorized security
tests.

### 2.2 Cross-site scripting (XSS)

**What it is:** Untrusted content is interpreted by a browser as
executable script.

**Common forms:** Stored XSS, reflected XSS, and DOM-based XSS.

**Potential impact:** Actions performed in a user's browser, exposure of
accessible page data, or misuse of an authenticated session.

**Defenses:** - Apply context-appropriate output encoding. - Use safe
framework rendering patterns; avoid unsafe HTML insertion. - Sanitize
HTML when rich user-authored HTML is genuinely required. - Deploy a
restrictive Content Security Policy (CSP) as an additional layer. - Set
cookies with appropriate `HttpOnly`, `Secure`, and `SameSite`
attributes. - Do not rely on input filtering alone.

### 2.3 Cross-site request forgery (CSRF)

**What it is:** A browser is induced to send an unwanted request using a
user's existing authenticated session.

**Potential impact:** Unintended changes made with the victim's
permissions.

**Defenses:** - Use framework-supported CSRF protection and anti-CSRF
tokens where applicable. - Set appropriate `SameSite` cookie
attributes. - Check `Origin` or `Referer` where appropriate as an
additional control. - Do not use GET requests for state-changing
actions. - Require re-authentication or confirmation for high-impact
actions. - Remember that CORS is not a substitute for CSRF protection.

### 2.4 Server-side request forgery (SSRF)

**What it is:** An application fetches a URL or resource chosen or
influenced by an untrusted user, allowing requests to destinations the
application should not reach.

**Potential impact:** Access to internal services, sensitive cloud
metadata, or unintended network resources.

**Defenses:** - Prefer allowlists of permitted destinations. - Block
loopback, private, link-local, and other internal address ranges unless
explicitly needed. - Validate DNS resolution and re-check destinations
after redirects. - Restrict outbound network access at the
infrastructure layer. - Disable redirects or validate every redirect
destination. - Set connection and response timeouts and response-size
limits. - Avoid exposing arbitrary URL-fetching features without a
strong business need.

### 2.5 Path traversal

**What it is:** User-controlled file paths escape an intended directory.

**Potential impact:** Unauthorized reading, overwriting, or deletion of
files.

**Defenses:** - Do not accept arbitrary filesystem paths from users. -
Map opaque file IDs to server-controlled paths. - Canonicalize paths and
verify the resolved path remains inside the permitted directory. - Run
services with restricted filesystem permissions. - Keep secrets and
configuration outside web-accessible directories.

### 2.6 Unsafe file uploads

**What it is:** File upload and processing features accept content that
is malicious, malformed, oversized, or unexpected.

**Potential impact:** Malware storage, parser vulnerabilities, denial of
service, data exposure, or unsafe content being served to users.

**Defenses:** - Allow only required file types. - Check file signatures
as well as claimed MIME types and extensions. - Set file-size,
page-count, decompression, and processing-time limits. - Generate
server-side filenames; do not trust supplied paths or names. - Store
uploads outside the web root and serve them through controlled
endpoints. - Scan files where appropriate and use isolated processing
environments. - Keep parsers and document-processing libraries
updated. - Treat extracted text and metadata as untrusted. - Apply
authorization to both upload and download operations.

### 2.7 Remote code execution (RCE)

**What it is:** A vulnerability allows untrusted input or a compromised
component to cause unintended code execution.

**Potential impact:** Application or server compromise, data theft,
service disruption, or lateral movement.

**Defenses:** - Avoid evaluating or executing untrusted input. - Avoid
shell commands where a library API is available. - If subprocesses are
necessary, use fixed executables and argument arrays, not
shell-concatenated strings. - Run services as non-root with minimal
permissions. - Isolate risky parsers, converters, and user code. - Patch
frameworks and dependencies promptly. - Apply network egress
restrictions and runtime monitoring.

### 2.8 Insecure deserialization

**What it is:** The application processes untrusted serialized objects
in an unsafe way.

**Potential impact:** Unexpected application behavior, authorization
problems, denial of service, or code execution in vulnerable
environments.

**Defenses:** - Prefer simple data formats and explicit schemas. - Do
not deserialize untrusted data into executable or polymorphic object
types. - Validate structure, types, sizes, and allowed fields. - Use
safe, maintained serialization libraries. - Authenticate and
integrity-protect data when appropriate.

### 2.9 Security misconfiguration

**What it is:** Unsafe defaults, unnecessary services, verbose errors,
exposed admin interfaces, or incorrect permissions leave the system
vulnerable.

**Defenses:** - Maintain secure configuration baselines. - Disable
unused features, ports, accounts, and endpoints. - Keep development
tools and debug modes out of production. - Review cloud storage,
firewall, database, and identity permissions. - Use automated
configuration checks. - Separate development, staging, and production
environments.
