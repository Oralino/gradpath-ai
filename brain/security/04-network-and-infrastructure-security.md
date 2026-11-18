# 04 Network And Infrastructure Security

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 5. Network and infrastructure threats

### 5.1 Distributed denial of service (DDoS)

**What it is:** Traffic or resource-intensive requests overwhelm a
service.

**Defenses:** - Use reputable hosting and DDoS protection. - Apply rate
limits, request limits, and timeouts. - Cache appropriate content. - Use
autoscaling carefully with budget controls. - Set quotas for expensive
endpoints and LLM usage. - Prepare an incident response and provider
escalation plan.

### 5.2 Man-in-the-middle (MITM) and traffic interception

**What it is:** Communications are intercepted or altered between
parties.

**Defenses:** - Use HTTPS/TLS everywhere, including internal service
connections where appropriate. - Configure modern TLS settings and renew
certificates. - Do not disable certificate validation. - Use secure
network configurations and trusted endpoints. - Avoid sending secrets
over plaintext channels.

### 5.3 DNS spoofing and IP spoofing

**What they are:** DNS responses or apparent source IP information are
falsified.

**Defenses:** - Use trusted DNS providers and secure DNS operations. -
Consider DNSSEC where appropriate. - Do not treat source IP as proof of
identity. - Use application-level authentication and authorization. -
Validate forwarded headers only from trusted proxies.

### 5.4 Port scanning and exposed services

**What it is:** Systems are probed to discover reachable services and
unnecessary exposure.

**Defenses:** - Expose only required services. - Use firewalls and
private network segments. - Restrict administrative interfaces. -
Inventory listening services and cloud security rules. - Monitor
unexpected network activity.

### 5.5 Supply-chain compromise

**What it is:** A dependency, build system, package, model, plugin, or
service is compromised and becomes a route into the application.

**Defenses:** - Use maintained dependencies from trusted sources. - Pin
and review dependency versions. - Generate and review a software bill of
materials (SBOM). - Scan dependencies and container images. - Protect
source control and CI/CD credentials. - Require review for dependency
and workflow changes. - Verify package provenance and signatures where
available. - Remove unused dependencies.
