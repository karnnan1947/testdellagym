# Dallah Gym – Design gaps & Odoo 20 adaptations

Modules: `dallah_gym_core` (DES00143), `dallah_gym_pos` (DES00144), `dallah_gym_zkbio` (DES00145),
plus `restricted_cost_access` (copied from alfiafyvet_test, already 20.0).

Launcher: `odoo20-dallah` (db `dallah_gym`, port 8072, config `odoo_20/odoo20/config/odoo20-dallah.conf`).

## Decisions taken (approved in chat)

| # | Gap in design | What was built |
|---|---------------|----------------|
| 1 | `res.branch` does not exist in Odoo 20 | New simple model `res.branch` in `dallah_gym_core` (name, code, company, analytic account) – a physical gym location, not a company. |
| 2 | `restricted_cost_access` not on the addons path | Copied from `alfiafyvet_test` (version 20.0.1.0.0). |
| – | Deferred revenue dates live in Enterprise | `account_accountant` added to `dallah_gym_core` depends. |
| – | POS API names in plan are from older Odoo | Odoo 20 equivalents: OWL `Dialog` + `makeAwaitable` (for `AbstractAwaitablePopup`), `_load_pos_data_fields` (for `_loader_params_*`), automatic field sync (for `_order_fields` / `_export_for_ui` / `export_as_JSON`), `PosStore.pay()` patch (for ProductScreen/Actionpad `pay()`), `GeneratePrinterData.generateReceiptData()` patch (for `export_for_printing`). |
| 3 | `gym.membership` fields not listed | partner, plan, branch, allowed branches, start/end, state, is_frozen, amount paid, coach, slot, sale line, POS line id, invoice, credit note. |
| 4 | "Auto-filled from Branch Policy" had no field | `res.branch.default_allowed_branch_ids`. |
| 5 | PT session generation rule | One session per coach working day (from coach split shifts at the branch covering the slot hour), from the start date, until N sessions or the plan end date. Coach with no shifts = every day. |
| 6 | "Tiered" reminders vs one `reminder_days_before` | Kept the design's single field per plan. |
| 7 | Credit note when POS sale was not invoiced | Draft standalone `out_refund` for the member; linked to the invoice (`reversed_entry_id`) when one exists. |
| 8 | Future-dated freeze | Followed design literally: turnstile suspended on confirm. |
| 9 | Branch record rules: no user↔branch link | `res.users.gym_branch_ids`; cashier/receptionist see own branches, `group_gym_manager` sees all. |
| 10 | Member code assignment | Sequence `GYM-<year>-XXXX` assigned when *Is Gym Member* is set. |
| 11 | One start date in modal vs per-line end dates | One start date for all lines; each line gets its own end date. |
| 12 | LQ-350 is not an ePOS printer | Receipt goes through the browser print dialog (Windows/CUPS LQ-350 driver). |
| 13 | "< 200 ms" test | Not measurable in unit tests; backend test checks cafeteria orders create no membership. |
| 14 | AppKey/AppSecret vs Bearer token | Bearer token only (as design). |
| 15 | Settings mapping table / "Turnstile Devices" had no field | `res.branch.zkbio_device_ids` + read-only mapping table in Settings with "Edit Branch Mapping" link. |
| 16 | `card_number` had no source field | `res.partner.zkbio_card_number`, falls back to QID. |
| 17 | Webhook secret had no setting | `zkbio_webhook_secret` (header `X-ZKBio-Token`). |
| 18 | ZKBio API paths | Used exactly as in design. **Ping path `/api/v1/system/ping` is an assumption – confirm with Allied.** Response parsing accepts `{"code":0,"data":[...]}` or a bare list. |

## Other small fills (no behaviour change to the design)

- Expired state: the 00:05 cron also moves memberships past their end date to *Expired* (no ZKBio call – ZKBio `end_time` already stops access).
- Coaches are loaded into the POS (needed for the coach dropdown) but flagged `_gym_coach_only`, so they can never log in as cashiers.
- Coach slot is re-checked on "Confirm & Proceed to Payment" so two counters cannot take the same slot (Task 5.3).
- POS membership finalization runs in a savepoint: a failure is logged and never blocks payment.
- POS invoice lines get the counter branch analytic account (design: "sets invoice analytic").
- Default slot hours when a coach has no shifts: Morning 09–13, Evening 16–20 (from the mockup).
- Extra menus/views not listed in the plans: Branches, Memberships list/form, Users "Gym Branches" tab.

## Odoo 20 specifics found while building/testing

- Security uses Odoo 20's merged `ir.access` model (`security/ir.access.csv`, columns `model_id,group_id/id,operation,domain`). Branch record rules are domains on the cashier rows; managers have no domain.
- `ir.config_parameter` is typed in Odoo 20 (`get_str/set_str/get_int/get_bool`), no `get_param/set_param`.
- POS order lines only sync an explicit field list: `membership_start_date, membership_end_date, coach_id, pt_slot_hour` added to `pos.order.line._load_pos_data_fields`.
- Cashiers without HR rights read employees through `hr.employee.public`, so `is_coach`, `allowed_branch_ids`, `coach_shift_ids`, `booking_horizon_days` are exposed there.
- Coach slot conflict checks and membership finalization run with `sudo()`: branch-restricted cashiers must still see a coach's bookings at other branches (no double booking) and a paid sale must always create its membership.
- Receipt No on the LQ-350 receipt uses the order name, falling back to the POS reference (Odoo 20 format `261-23-000002`), not the `POS/2026/0892` style of the mockup – a custom sequence would be needed for that exact format.

## Tests (all passing: `odoo20-dallah -d dallah_gym -u <modules> --test-tags /dallah_gym_core,/dallah_gym_pos,/dallah_gym_zkbio --stop-after-init`)

- core: end date (5.1), freeze math (5.2), restore cron (5.3), PT conflict (5.4), pro-rata 66.67 (5.5), PT session generation, member code; browser: PT Reception Board, member form.
- pos: cafeteria bypass, counter defaults in POS payload, multi-terminal slot lock, paid order → membership; browser tour `DallahGymCheckoutTour` (cafeteria skips modal → membership+PT modal → coach/slot → pay → LQ-350 receipt values).
- zkbio: offline queue (5.1), queue recovery (5.2), freeze/refund endpoints, scan importer dedup (5.3); browser: settings page.
- Browser tests need a Chromium binary named `chromium`/`google-chrome` on PATH (Brave works via symlink).
- Not covered automatically: live ZKBio hardware UAT and physical LQ-350 print alignment (Tasks 5.4).
