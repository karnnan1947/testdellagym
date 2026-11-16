import { Component, onWillStart, proxy, useProps, t } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { computeGymEndDate } from "./models";

const { DateTime } = luxon;

/**
 * Single unified pre-payment modal (Membership & PT checkout confirmation).
 * Opened ONCE when clicking "Payment" if the cart contains a membership / PT product.
 * Resolves with the confirmed payload, or nothing when "Back to Cart" is used.
 */
export class GymCheckoutModal extends Component {
    static template = "dallah_gym_pos.GymCheckoutModal";
    static components = { Dialog };
    props = useProps({
        order: t.object(),
        close: t.function(),
        getPayload: t.function(),
    });

    setup() {
        this.pos = usePos();
        const config = this.pos.config;
        const order = this.props.order;
        const firstPt = order.getGymPtLines()[0];
        const existingStart = order.getGymLines().find((l) => l.membership_start_date)?.membership_start_date;
        this.state = proxy({
            startDate: existingStart ? String(existingStart) : DateTime.now().toISODate(),
            allowedBranchIds: new Set(
                (order.allowed_branch_ids?.length
                    ? order.allowed_branch_ids
                    : config.default_allowed_branch_ids || []
                ).map((b) => b.id)
            ),
            ptBranchId: config.gym_branch_id?.id || false,
            coachId: firstPt?.coach_id?.id || false,
            slotHour: firstPt?.pt_slot_hour || false,
            slots: { morning: [], evening: [] },
            loadingSlots: false,
            error: "",
        });
        onWillStart(async () => {
            if (this.hasPt && this.state.coachId) {
                await this.loadSlots();
            }
        });
    }

    get order() {
        return this.props.order;
    }

    get member() {
        return this.order.getPartner();
    }

    get counterName() {
        return this.pos.config.name;
    }

    get branches() {
        return this.pos.models["res.branch"].getAll();
    }

    get gymLines() {
        return this.order.getGymLines();
    }

    get ptLines() {
        return this.order.getGymPtLines();
    }

    get hasPt() {
        return this.ptLines.length > 0;
    }

    get totalSessions() {
        return Math.max(...this.ptLines.map((l) => l.product_id.pt_total_sessions || 0), 1);
    }

    get coaches() {
        const branchId = this.state.ptBranchId;
        return this.pos.models["hr.employee"].filter(
            (emp) =>
                emp.is_coach &&
                (!branchId || (emp.allowed_branch_ids || []).some((b) => b.id === branchId))
        );
    }

    endDateFor(line) {
        const end = computeGymEndDate(line.product_id, this.state.startDate);
        return end?.isValid ? end.toISODate() : "";
    }

    get ptEndDate() {
        const ends = this.ptLines.map((l) => this.endDateFor(l)).filter(Boolean).sort();
        return ends[ends.length - 1] || false;
    }

    isBranchChecked(branch) {
        return this.state.allowedBranchIds.has(branch.id);
    }

    toggleBranch(branch) {
        const ids = new Set(this.state.allowedBranchIds);
        ids.has(branch.id) ? ids.delete(branch.id) : ids.add(branch.id);
        this.state.allowedBranchIds = ids;
    }

    async onStartDateChange(ev) {
        this.state.startDate = ev.target.value || DateTime.now().toISODate();
        if (this.hasPt && this.state.coachId) {
            await this.loadSlots();
        }
    }

    async onPtBranchChange(ev) {
        this.state.ptBranchId = parseInt(ev.target.value) || false;
        if (!this.coaches.some((c) => c.id === this.state.coachId)) {
            this.state.coachId = false;
            this.state.slotHour = false;
            this.state.slots = { morning: [], evening: [] };
        } else {
            await this.loadSlots();
        }
    }

    async onCoachChange(ev) {
        this.state.coachId = parseInt(ev.target.value) || false;
        this.state.slotHour = false;
        await this.loadSlots();
    }

    /** One batch RPC: coach slot availability for the whole PT package. */
    async loadSlots() {
        if (!this.state.coachId) {
            this.state.slots = { morning: [], evening: [] };
            return this.state.slots;
        }
        this.state.loadingSlots = true;
        try {
            const res = await this.pos.data.call("gym.membership.service", "get_branch_coach_slots", [
                this.state.ptBranchId || false,
                this.state.coachId,
                this.state.startDate,
                this.totalSessions,
                this.ptEndDate,
            ]);
            this.state.slots = { morning: res.morning || [], evening: res.evening || [] };
            const selected = [...this.state.slots.morning, ...this.state.slots.evening].find(
                (s) => s.hour === this.state.slotHour
            );
            if (selected?.booked) {
                this.state.slotHour = false;
            }
        } finally {
            this.state.loadingSlots = false;
        }
        return this.state.slots;
    }

    slotClass(slot) {
        if (slot.hour === this.state.slotHour) {
            return "btn-primary";
        }
        return slot.booked ? "btn-danger disabled" : "btn-outline-success";
    }

    selectSlot(slot) {
        if (!slot.booked) {
            this.state.slotHour = slot.hour;
        }
    }

    async confirm() {
        this.state.error = "";
        if (!this.state.allowedBranchIds.size && this.gymLines.some((l) => l.product_id.membership_type === "gym")) {
            this.state.error = _t("Select at least one branch turnstile.");
            return;
        }
        if (this.hasPt) {
            if (!this.state.coachId || this.state.slotHour === false) {
                this.state.error = _t("Select a coach and a 1-hour slot for the PT package.");
                return;
            }
            // Re-check right before confirming: another counter may have taken the slot meanwhile.
            const slots = await this.loadSlots();
            const slot = [...slots.morning, ...slots.evening].find((s) => s.hour === this.state.slotHour);
            if (!slot || slot.booked) {
                this.state.slotHour = false;
                this.state.error = _t("This slot was just booked at another counter. Please pick another slot.");
                return;
            }
        }
        this.props.getPayload({
            startDate: this.state.startDate,
            allowedBranchIds: [...this.state.allowedBranchIds],
            ptBranchId: this.state.ptBranchId,
            coachId: this.state.coachId,
            slotHour: this.state.slotHour,
            endDates: Object.fromEntries(this.gymLines.map((l) => [l.uuid, this.endDateFor(l)])),
        });
        this.props.close();
    }
}
