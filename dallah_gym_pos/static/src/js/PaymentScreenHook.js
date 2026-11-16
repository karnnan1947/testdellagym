import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { GymCheckoutModal } from "./GymCheckoutModal";

/**
 * Smart payment interception:
 *  - cafeteria / retail carts go straight to the Payment Screen (no RPC, no modal);
 *  - carts with a membership / PT product open the single GymCheckoutModal first.
 */
patch(PosStore.prototype, {
    async pay() {
        const order = this.getOrder();
        if (!order || !order.hasMembershipOrPtProduct()) {
            return super.pay(...arguments);
        }
        if (!order.canPay()) {
            return;
        }
        if (!order.getPartner()) {
            this.dialog.add(AlertDialog, {
                title: _t("Member required"),
                body: _t("Please select the member (customer) before selling a membership or PT package."),
            });
            return;
        }
        const payload = await makeAwaitable(this.dialog, GymCheckoutModal, { order });
        if (!payload) {
            return; // Back to Cart
        }
        this.applyGymCheckoutPayload(order, payload);
        return super.pay(...arguments);
    },

    applyGymCheckoutPayload(order, payload) {
        const Branch = this.models["res.branch"];
        const Employee = this.models["hr.employee"];
        order.allowed_branch_ids = payload.allowedBranchIds.map((id) => Branch.get(id)).filter(Boolean);
        order.gym_branch_id = this.config.gym_branch_id || false;
        const coach = payload.coachId ? Employee.get(payload.coachId) : false;
        for (const line of order.getGymLines()) {
            line.membership_start_date = payload.startDate;
            line.membership_end_date = payload.endDates[line.uuid] || payload.startDate;
            if (["pt", "class"].includes(line.product_id.membership_type)) {
                line.coach_id = coach || false;
                line.pt_slot_hour = payload.slotHour || 0;
            }
        }
    },
});
