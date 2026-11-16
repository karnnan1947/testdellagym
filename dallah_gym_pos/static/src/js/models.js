import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";
import { formatDate } from "@web/core/l10n/dates";
import { PosTicketPrinterPlugin } from "@point_of_sale/app/plugins/pos_ticket_printer_plugin";

const { DateTime } = luxon;

/**
 * Same rule as gym.membership._end_date_for(): start + duration - 1 day.
 */
export function computeGymEndDate(product, startDate) {
    const value = product.membership_duration_val || 0;
    const unit = product.membership_duration_unit || "months";
    const start = typeof startDate === "string" ? DateTime.fromISO(startDate) : startDate;
    if (!value || !start?.isValid) {
        return start;
    }
    return start.plus({ [unit]: value }).minus({ days: 1 });
}

export function formatGymHour(hour) {
    if (hour === undefined || hour === null || hour === false) {
        return "";
    }
    const h = Math.floor(hour);
    const m = Math.round((hour - h) * 60);
    const suffix = h < 12 ? "AM" : "PM";
    const h12 = h % 12 || 12;
    return `${String(h12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${suffix}`;
}

patch(PosOrder.prototype, {
    /** True only if at least one cart line is a gym membership / PT / class product. */
    hasMembershipOrPtProduct() {
        return this.getOrderlines().some((line) => line.product_id?.is_gym_membership === true);
    },
    getGymLines() {
        return this.getOrderlines().filter((line) => line.product_id?.is_gym_membership === true);
    },
    getGymPtLines() {
        return this.getGymLines().filter((line) =>
            ["pt", "class"].includes(line.product_id.membership_type)
        );
    },
});

patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const data = super.generateReceiptData(...arguments);
        const order = this.order;
        const gymLines = order.getGymLines ? order.getGymLines() : [];
        const fmt = (d) => (d ? formatDate(DateTime.fromISO(String(d)), { format: "dd-MMM-yyyy" }) : "");
        const ptLine = gymLines.find((l) => l.coach_id);
        const starts = gymLines.map((l) => l.membership_start_date).filter(Boolean).map(String).sort();
        const ends = gymLines.map((l) => l.membership_end_date).filter(Boolean).map(String).sort();
        const cashier = order.getCashierName ? order.getCashierName() : "";
        const branch = order.gym_branch_id || this.config.gym_branch_id;
        data.extra_data.gym = {
            receipt_no: (order.name && order.name !== "/" ? order.name : order.pos_reference) || "",
            date: (order.date_order?.toFormat ? order.date_order : DateTime.now()).toFormat(
                "dd-MMM-yyyy HH:mm"
            ),
            member_name: order.partner_id?.name || "",
            member_code: order.partner_id?.member_id_code || "",
            plan: order.getOrderlines().map((l) => l.getFullProductName()).join(" + "),
            start_date: fmt(starts[0]),
            end_date: fmt(ends[ends.length - 1]),
            coach_name: ptLine?.coach_id?.name || "",
            coach_slot: ptLine ? formatGymHour(ptLine.pt_slot_hour) : "",
            amount: this.formatCurrency(order.priceIncl ?? order.displayPrice),
            payment_methods: order.payment_ids
                .filter((p) => !p.is_change)
                .map((p) => p.payment_method_id?.name)
                .filter(Boolean)
                .join(", "),
            cashier_name: cashier,
            branch_name: branch?.name || "",
        };
        return data;
    },
});

/**
 * Epson LQ-350 continuous 3-ply pre-printed form: when enabled on the counter,
 * receipts use the coordinate-mapped dot-matrix layout and go through the
 * browser print dialog (LQ-350 is a driver printer, not an ePOS thermal printer).
 */
patch(PosTicketPrinterPlugin.prototype, {
    async printOrderReceipt({ order, basic = false, printBillActionTriggered = false, simplified = false } = {}) {
        if (!this.config?.use_dot_matrix_receipt) {
            return super.printOrderReceipt(...arguments);
        }
        const data = this.getOrderReceiptData(order, { basic, simplified });
        const iframe = await this.generateIframe("dallah_gym_pos.EpsonLQ350Receipt", data);
        this.printWeb(iframe);
        if (!printBillActionTriggered) {
            await this.markReceiptAsPrinted(order);
        }
        return { successful: true };
    },
});
