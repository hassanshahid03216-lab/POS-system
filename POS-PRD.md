# Product Requirements Document (PRD)
## ShopFlow POS — Fast, Offline Desktop POS with Insights

**Author:** Hassan Shahid
**Date:** September 25, 2026
**Status:** Draft v1

---

## 1. Problem Statement
Most small individual shops in Pakistan (kiryana stores, mobile shops, pharmacies, boutiques) still use manual registers or Excel. Existing POS software is either:
- Too expensive / subscription-locked
- Requires constant internet
- Slow on the low-end PCs common in these shops
- Gives no real insight into sales, stock, or profit

**Goal:** Build a lightweight, offline-first Windows desktop POS that shopkeepers can install once, use on old hardware without lag, and get real business insights from — sold as a one-time/low-cost product you can pitch directly to shop owners.

---

## 2. Target Users
| User | Needs |
|---|---|
| Shop owner | Fast billing, stock tracking, daily profit/sales insight, low cost |
| Cashier/staff | Simple billing screen, minimal training needed |
| Hassan (you) | A sellable, demoable product for individual shop sales & portfolio |

---

## 3. Goals & Success Metrics
- Bill a customer in **under 10 seconds** for a typical 5-item cart
- App launches and is usable in **under 3 seconds** on a low-spec PC (4GB RAM)
- Works **fully offline**, no internet dependency for core billing
- Shop owner can see "how's my shop doing today" in **one screen**
- First 5 real shop installs within 2 months of MVP

---

## 4. Core Features (MVP)

### 4.1 Billing / Point of Sale
- Add items via barcode scan or search
- Quantity, discount, tax per item
- Multiple payment modes: Cash, Card, JazzCash/EasyPaisa (manual entry)
- Print/save receipt (thermal printer support + PDF fallback)
- Hold/resume a bill (for multitasking at counter)

### 4.2 Inventory Management
- Add/edit products (name, SKU/barcode, cost price, sale price, stock qty, category)
- Low-stock alerts
- Bulk import via CSV/Excel

### 4.3 Insights Dashboard
- Today/Week/Month sales total & profit
- Best-selling & slow-moving items
- Peak sale hours (helps staffing)
- Stock value on hand
- Simple charts (bar/line) — no clutter, one glance = one insight

### 4.4 Users & Roles
- Admin (owner): full access, insights, settings
- Cashier: billing screen only, no access to reports/settings

### 4.5 Data & Backup
- All data stored locally (SQLite) — instant, no lag
- One-click local backup/export (to USB/Drive)
- Optional cloud backup (later phase)

---

## 5. Non-Functional Requirements
- **Performance:** every screen transition < 200ms; no visible lag on 4GB RAM / old i3 PCs
- **Offline-first:** zero required internet for daily use
- **Reliability:** no data loss on crash/power cut (auto-save/transaction log at DB level)
- **Simplicity:** a shopkeeper with no tech background should onboard in <15 minutes
- **Footprint:** installer under ~150MB, low CPU/RAM usage idle

---

## 6. Out of Scope (v1)
- Multi-branch sync / cloud dashboard (phase 2)
- Online store / e-commerce integration
- Accounting/tax filing compliance features
- Mobile app version

---

## 7. Monetization Plan
- One-time license fee per shop (simple activation key) — matches how you're pitching shop-to-shop
- Optional: paid add-on later for cloud multi-branch dashboard or WhatsApp sales reports
- No subscription friction for MVP — easier sell to individual shop owners

---

## 8. Risks
| Risk | Mitigation |
|---|---|
| Shop owners resist switching from manual register | Free trial period + very short onboarding |
| Old PCs / low hardware | Keep stack native-feeling & lightweight (see tech doc) |
| Piracy of license key | Simple hardware-locked activation |
| Barcode/printer hardware variance | Support common ESC/POS thermal printers + generic barcode scanners (act as keyboard input) |

---

## 9. Milestones
1. **Week 1–2:** Billing screen + local DB + product management
2. **Week 3:** Insights dashboard v1
3. **Week 4:** Printing, backup, roles/login
4. **Week 5:** Polish, packaging, installer
5. **Week 6:** Pilot with 2–3 real shops, gather feedback
