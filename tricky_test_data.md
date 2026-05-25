# 🧪 Tricky Test Data for QA-Genius

> One happy path + one tricky/edge case per tab.

---

## 📝 1. Story Analyzer

### Happy Path
```
As a registered user, I want to reset my password via email
so that I can regain access to my account if I forget it.

Acceptance Criteria:
- User enters registered email and clicks "Forgot Password"
- System sends a reset link valid for 24 hours
- Link redirects to a secure password reset page
- New password must be 8+ chars with 1 uppercase, 1 number, 1 symbol
- User sees confirmation message after successful reset
```

### Tricky / Edge Case
```
As a user I want the system to be fast and secure so that everything works good.
```
*Why:* Extremely vague, no acceptance criteria, missing all INVEST qualities.

---

## 🧪 2. Test Cases

### Happy Path
```
As a customer, I want to apply a discount coupon during checkout
so that I can get a reduced price on my order.

Rules:
- Coupon code is case-insensitive
- One coupon per order
- Cannot combine with other promotions
- Expired coupons show "This coupon has expired" error
- Invalid coupons show "Invalid coupon code" error
```
Tech Stack: `React + Node.js + PostgreSQL`

### Tricky / Edge Case
```
User uploads a file. File should be big but also small. 
Must support all formats. Should process instantly even if 10GB. 
If upload fails, retry forever. Show progress but also don't show progress.
```
*Why:* Conflicting requirements, impossible constraints.

---

## 🐛 3. Bug Report

### Happy Path
```
Login fails sometimes on mobile. User enters correct credentials, 
taps login, spinner shows for 2s then disappears. No error message. 
User stays on login screen. Happens about 3 out of 5 tries on my iPhone. 
Works fine on desktop. Started happening after yesterday's deploy.
```
- Device: Mobile | OS: iOS 17.4 | Browser: Safari 17
- Total attempts: 5 | Successful attempts: 2

### Tricky / Edge Case
```
thing broke. fix it asap. users complaining.
```
- Device: Not specified | OS: (empty) | Browser: (empty)
- Total attempts: 10 | Successful attempts: 10
*Why:* Vague notes + success = total (triggers your warning banner).

---

## 📊 4. Quality Analytics

### Happy Path
- Passed: 287 | Failed: 32 | Blocked: 8 | Skipped: 3
- Failure breakdown:
  ```
  checkout flow — 14 — discount code race condition
  search filters — 9 — new feature stabilization
  login — 3 — third-party OAuth timeout
  ```
- Blocker breakdown:
  ```
  5 — sandbox down — DevOps
  3 — dependency not ready — Backend
  ```
- QA capacity: 4.0 | Carryover bugs: 12

### Tricky / Edge Case
- Passed: 0 | Failed: 0 | Blocked: 0 | Skipped: 0
- Failure breakdown: `Everything is broken`
- Blocker breakdown: *(empty)*
- QA capacity: 0.5 | Carryover bugs: 999
*Why:* All zeros test division-by-zero guard + garbage format handling.

---

## ⚙️ 5. Automation Script

### Happy Path
```
Login test for an e-commerce site: valid login with correct credentials,
invalid password shows error message, empty fields show validation errors,
account lockout after 5 failed attempts, remember me checkbox persists session.
```
- Framework: Playwright (Python) | Structure: Page Object Model | Browsers: Chromium, Firefox

### Tricky / Edge Case
```
Test the app. Make sure it works. Test everything.
```
- Framework: Playwright (Python) | Structure: Flat scripts | Browsers: Chromium
*Why:* Extremely vague scenario with minimal structure.

---

## 🔍 6. Schema Validator

### Happy Path
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "role": "admin",
  "created_at": "2024-01-15T10:30:00Z",
  "profile_picture": "https://cdn.example.com/avatars/123.jpg"
}
```
Expected Schema: `user_id integer, email non-null valid email, role in [user, admin, moderator], created_at ISO 8601, profile_picture HTTPS URL, is_active boolean should exist`

### Tricky / Edge Case
```json
{
  "user_id": "not-a-number",
  "email": null,
  "role": "super_admin_hacker",
  "created_at": "yesterday",
  "password": "plaintext123",
  "ssn": "123-45-6789",
  "credit_card": "4111111111111111"
}
```
*Why:* Type mismatches, nulls, PII leakage, invalid enums — tests all validation layers.

---

## 🔒 7. Security Tests

### Happy Path
```
E-commerce platform with React frontend, Node.js + Express API,
MongoDB database, JWT authentication, Stripe payments, file upload for
product images, admin dashboard for inventory management.
```
- App Type: Web Application | Auth: JWT | Features: Authentication, Payments, File Upload | Compliance: PCI-DSS

### Tricky / Edge Case
```
It's a website.
```
- App Type: Web Application | Auth: API Keys | Features: *(none)* | Compliance: None / Not Sure
*Why:* Minimal description with no features selected.

---

## ⚡ 8. Performance Tests

### Happy Path
```
1. POST /api/auth/login with email+password
2. GET /api/products/search?q=laptop
3. POST /api/cart/items with product_id
4. POST /api/checkout with Stripe token
Think time: 1-2s between steps
```
- Expected Users: 5000 | Peak Event: Black Friday / Flash Sale
- SLA: `p95 latency < 300ms, error rate < 0.5%, throughput > 1000 RPS`
- Endpoint SLAs: `/api/auth/login | 200ms | 500ms` `/api/products | 300ms | 600ms`

### Tricky / Edge Case
```
Users do stuff. Some click things. Others scroll.
Sometimes they buy. Usually they just look.
```
- Expected Users: 999999999 | Peak Event: Custom — `TikTok viral spike, 1000x for 15min then silence`
- SLA: `p99 latency < 1ms, error rate < 0%, throughput > 10000000 RPS`
*Why:* Vague flows + impossible SLAs + extreme user count.

---

## 🔥 Bonus: Chaos Input (paste in ANY tab)

```
As a 用户, I want the システム to handle 💰 payments via 
<script>alert(1)</script> with NULL values and 999999999 
concurrent users at p99 < 1ms latency while storing 
SSN 123-45-6789 in plaintext. Also login should both 
work and not work. Fix it yesterday. 🚀🔥💀
```
*Why:* Watch how each tab handles the same chaos differently.
