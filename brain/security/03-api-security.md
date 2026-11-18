# 03 Api Security

> Defensive cybersecurity reference. Test only systems you own or are explicitly authorized to assess.

## 4. API security threats

APIs are a major attack surface because they expose application
functionality and data.

### Common API risks

  -----------------------------------------------------------------------
  Risk                    Meaning                 Defenses
  ----------------------- ----------------------- -----------------------
  Broken Object Level     User accesses another   Check ownership and
  Authorization (BOLA)    user's object           permission on every
                                                  object request

  Broken Function Level   User invokes a function Enforce role and action
  Authorization (BFLA)    reserved for another    checks server-side
                          role                    

  Broken authentication   Weak or incorrectly     Use established
                          implemented identity    identity libraries,
                          checks                  MFA, secure token
                                                  handling

  Excessive data exposure API returns more data   Explicit response
                          than the caller needs   schemas and field-level
                                                  authorization

  Mass assignment         Client changes fields   Allowlist writable
                          it should not control   fields; use dedicated
                                                  request models

  Unrestricted resource   Requests consume        Rate, size,
  consumption             excessive CPU, memory,  concurrency, and cost
                          tokens, or money        limits

  Improper inventory      Old or undocumented API Maintain an API
  management              versions remain exposed inventory and retire
                                                  obsolete versions

  Unsafe API consumption  Third-party responses   Validate schemas,
                          are trusted without     authenticate providers,
                          validation              limit destinations and
                                                  data
  -----------------------------------------------------------------------

**General API defenses:** - Authenticate and authorize every protected
endpoint. - Validate request schemas, types, lengths, and allowed
values. - Use explicit response models and avoid returning internal
fields. - Apply rate limits, quotas, pagination limits, and timeouts. -
Use TLS. - Keep an inventory of endpoints and versions. - Log
security-relevant events without logging secrets. - Validate third-party
API responses as untrusted input.
