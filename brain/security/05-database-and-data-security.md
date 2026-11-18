# 05 Database And Data Security

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 6. Database and data threats

### 6.1 Data exfiltration and data breaches

**What they are:** Sensitive information is accessed or extracted
without authorization.

**Defenses:** - Enforce access control at every data access point. -
Encrypt data in transit and at rest. - Minimize collected and retained
information. - Restrict exports and bulk queries. - Monitor unusual
access and downloads. - Protect backups and logs. - Have a documented
breach response process.

### 6.2 Data tampering

**What it is:** Unauthorized modification or deletion of information.

**Defenses:** - Apply least-privilege database roles. - Use transactions
and integrity constraints. - Audit sensitive changes. - Protect backups
and use tested recovery procedures. - Require approval for high-impact
administrative operations.

### 6.3 Data poisoning

**What it is:** An attacker introduces misleading or malicious data into
a dataset, training corpus, or knowledge base.

**Defenses:** - Restrict data contributors and ingestion sources. -
Track provenance, ownership, timestamps, and versions. - Validate and
review content before ingestion. - Maintain rollback and deletion
workflows. - Monitor for unusual changes and retrieval behavior. -
Separate trusted sources from unreviewed content.

### 6.4 Backup exposure

**What it is:** Backups are exposed through weak permissions, public
storage, or inadequate protection.

**Defenses:** - Encrypt backups. - Restrict backup access separately
from production access. - Keep protected, versioned, and preferably
immutable copies. - Test restoration regularly. - Apply retention and
deletion policies.

### 6.5 Cryptographic weaknesses

**What they are:** Weak algorithms, poor key management, insecure
randomness, or incorrect cryptographic use.

**Defenses:** - Use established cryptographic libraries and modern,
well-reviewed algorithms. - Do not invent custom cryptography. - Store
keys in a secrets manager or key management service. - Rotate keys and
restrict who can use them. - Use cryptographically secure randomness for
tokens. - Plan key backup, revocation, and recovery.
