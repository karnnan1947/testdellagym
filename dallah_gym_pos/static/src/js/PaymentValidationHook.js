import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Re-check the coach slots on the server right before the order is validated.
 * Another terminal may have taken the slot since this terminal's checkout modal was opened;
 * rejecting here keeps the order open (the cashier can go back and pick another slot) instead
 * of leaving a paid-but-rejected order stuck in the POS sync queue.
 */
patch(OrderPaymentValidation.prototype, {
    async isOrderValid() {
        const valid = await super.isOrderValid(...arguments);
        if (!valid) {
            return false;
        }
        const ptLines = this.order.getGymPtLines ? this.order.getGymPtLines() : [];
        const lines = ptLines
            .filter((line) => line.coach_id && line.pt_slot_hour)
            .map((line) => ({
                product_id: line.product_id.id,
                coach_id: line.coach_id.id,
                pt_slot_hour: line.pt_slot_hour,
                membership_start_date: line.membership_start_date
                    ? String(line.membership_start_date)
                    : false,
                membership_end_date: line.membership_end_date
                    ? String(line.membership_end_date)
                    : false,
            }));
        if (!lines.length) {
            return true;
        }
        const branchId = this.order.gym_branch_id?.id || this.pos.config.gym_branch_id?.id || false;
        try {
            await this.pos.data.call("gym.membership.service", "check_slots", [branchId, lines]);
        } catch (error) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Coach slot no longer available"),
                body:
                    error?.data?.message ||
                    error?.message ||
                    _t("The selected coach slot has just been booked. Please choose another slot."),
            });
            return false;
        }
        return true;
    },
});
