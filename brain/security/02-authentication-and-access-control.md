# 02 Authentication And Access Control

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 3. Authentication, session, and authorization threats

### 3.1 Brute-force attacks

**What it is:** Repeated attempts to guess credentials.

**Defenses:** - Rate-limit login and recovery endpoints. - Use
progressive delays and risk-based challenges. - Support multi-factor
authentication (MFA). - Monitor unusual login patterns. - Avoid
account-lockout policies that enable easy denial of service.

### 3.2 Credential stuffing

**What it is:** Reuse of credentials exposed in unrelated breaches.

**Defenses:** - Require unique passwords and encourage password
managers. - Support MFA or passkeys. - Screen new passwords against
known-compromised password lists using a privacy-conscious service or
local dataset. - Detect unusual login patterns and provide safe account
recovery.

### 3.3 Password spraying

**What it is:** A small set of common passwords is tried against many
accounts.

**Defenses:** - MFA or passkeys. - Rate limits across both account and
source dimensions. - Monitoring for distributed authentication
failures. - Strong password policy focused on length and
compromised-password screening.

### 3.4 Session hijacking and session fixation

**What they are:** An attacker misuses a valid session or causes a
victim to use a session identifier known to the attacker.

**Defenses:** - Use secure, unpredictable session identifiers. - Rotate
session IDs after login and privilege changes. - Set `Secure`,
`HttpOnly`, and appropriate `SameSite` cookie attributes. - Use short,
risk-appropriate session lifetimes and revoke sessions on logout. -
Protect tokens from browser storage and script exposure where
possible. - Require re-authentication for sensitive actions. - Use HTTPS
throughout.

### 3.5 Broken access control and privilege escalation

**What they are:** A user accesses data or functionality beyond their
permissions, or obtains higher privileges than intended.

**Examples:** IDOR (Insecure Direct Object Reference) and BOLA (Broken
Object Level Authorization) occur when a user can access an object they
do not own or have permission to use.

**Defenses:** - Enforce authorization on the server for every object and
action. - Derive identity from the authenticated session, not
client-supplied identity fields. - Check ownership, tenant, role, and
action permission on every request. - Deny by default. - Avoid relying
on hidden buttons, unguessable IDs, or frontend checks. - Test with
multiple users and roles, including attempts to access each other's
records. - Review privilege changes and administrative actions.

### Authentication versus authorization

-   **Authentication:** Who is making the request?
-   **Authorization:** Is that identity allowed to perform this action
    on this resource?

A successful login does not grant access to every record or operation.
