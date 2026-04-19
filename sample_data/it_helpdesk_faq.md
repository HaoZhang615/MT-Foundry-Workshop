# Contoso IT Helpdesk – Knowledge Base

## Password & Account Management

| Topic | Policy |
|-------|--------|
| Password resets | Self-service via https://passwordreset.contoso.com. Requires MFA. If locked out, contact the helpdesk. |
| Password requirements | Minimum 14 characters, at least one uppercase, one number, one special character. Expires every 90 days. |
| Account lockout | After 5 failed attempts the account locks for 30 minutes. Helpdesk can unlock immediately. |
| MFA enrollment | All employees must enroll in Microsoft Authenticator within 7 days of onboarding. SMS fallback is disabled. |
| Shared mailbox access | Request via ServiceNow catalog. Manager approval required. Provisioned within 4 business hours. |

## VPN & Remote Access

- **Supported client:** Contoso VPN Client v4.2+ (Windows, macOS, Linux).
- **Connection steps:** Launch client → sign in with Entra ID → select nearest gateway → connect.
- **Split tunneling:** Enabled by default. Internal apps (*.contoso.com) route through VPN; all other traffic goes direct.
- **Troubleshooting:** If connection drops, flush DNS (`ipconfig /flushdns` on Windows, `sudo dscacheutil -flushcache` on macOS), restart the client, and retry.
- **Firewall ports:** Outbound UDP 443 and TCP 8443 must be open on the user's network.

## Software Requests

1. Browse the **Software Catalog** in ServiceNow → Request Items.
2. Select the application and business justification.
3. Approvals: manager (all requests) + Security team (for privileged tools like Wireshark, Postman, Docker Desktop).
4. SLA: Standard software provisioned within 1 business day; privileged software within 3 business days.
5. Unsupported software: If an app is not in the catalog, submit a "New Software Evaluation" request. Evaluation takes up to 10 business days.

## Hardware & Equipment

| Item | Process | SLA |
|------|---------|-----|
| Laptop replacement | Submit hardware request in ServiceNow. Old device must be returned within 5 days. | 3 business days |
| Monitor / peripherals | Self-order from IT vending kiosk (Building 3, Floor 1) or request online. | Same day (kiosk) / 2 days (shipped) |
| Mobile device | Manager-approved request. Device enrolled in Intune MDM before use. | 2 business days |
| Loaner equipment | Available for up to 14 days. Extensions require director approval. | Same day pickup |

## Incident Escalation

- **Priority 1 (Critical):** Service outage affecting >50 users. Response: 15 minutes. Auto-escalates to on-call engineer.
- **Priority 2 (High):** Service degraded or single user completely blocked. Response: 1 hour.
- **Priority 3 (Medium):** Inconvenience but workaround exists. Response: 4 business hours.
- **Priority 4 (Low):** General questions, how-to requests. Response: 1 business day.

Escalation path: L1 Helpdesk → L2 Engineering → L3 Platform Team → VP of IT (for Priority 1 only).

## Supported Applications & Versions

| Application | Supported Version | Notes |
|------------|-------------------|-------|
| Microsoft 365 | Latest channel | Auto-updated via Intune |
| Microsoft Teams | Latest | Desktop app required for meetings |
| Visual Studio Code | Latest stable | Extensions managed via policy |
| Python | 3.11, 3.12 | Installed via Software Catalog |
| Docker Desktop | 4.x | Requires Security approval |
| Zoom | Not supported | Use Teams instead |

## Contact & Hours

- **Helpdesk Portal:** https://helpdesk.contoso.com
- **Email:** itsupport@contoso.com
- **Phone:** +1-800-555-0199
- **Hours:** Monday–Friday 06:00–22:00 UTC. Weekend on-call for Priority 1 only.
- **Walk-in:** Building 3, Floor 1, Room 101. No appointment needed during business hours.
