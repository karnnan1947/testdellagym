import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as FeedbackScreen from "@point_of_sale/../tests/pos/tours/utils/feedback_screen_util";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("DallahGymCheckoutTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            // 1. Cafeteria cart: no modal, straight to the Payment Screen
            ProductScreen.addOrderline("Bottled Water", "1"),
            ProductScreen.clickPayButton(),
            {
                content: "no gym checkout modal for cafeteria orders",
                trigger: ".payment-screen",
                run() {
                    if (document.querySelector(".o_gym_checkout_modal")) {
                        throw new Error("Gym modal must not open for cafeteria orders");
                    }
                },
            },
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            FeedbackScreen.isShown(),
            FeedbackScreen.clickNextOrder(),

            // 2. Membership + PT cart: single pre-payment modal
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("Nasser Al-Kuwari"),
            ProductScreen.addOrderline("6 Months Full Gym", "1"),
            ProductScreen.addOrderline("PT 26", "1"),
            ProductScreen.clickPayButton(false),
            {
                content: "gym checkout modal is shown",
                trigger: ".o_gym_checkout_modal:contains(MEMBERSHIP & PT CHECKOUT CONFIRMATION)",
            },
            {
                content: "counter default turnstiles are pre-checked (BBM)",
                trigger: ".o_gym_checkout_modal label:contains(BBM) input:checked",
            },
            {
                content: "ladies gym is not pre-checked",
                trigger: ".o_gym_checkout_modal label:contains(LAD) input:not(:checked)",
            },
            {
                content: "select coach",
                trigger: ".o_gym_checkout_modal select:has(option:contains(Coach Alex Rodriguez))",
                run: "selectByLabel Coach Alex Rodriguez",
            },
            {
                content: "pick the free 07-08 evening slot",
                trigger: ".o_gym_checkout_modal .o_gym_slot:contains(07-08):not(.disabled)",
                run: "click",
            },
            {
                content: "slot is selected",
                trigger: ".o_gym_checkout_modal .o_gym_slot.btn-primary:contains(07-08)",
            },
            {
                content: "confirm and proceed to payment",
                trigger: ".o_gym_checkout_modal button:contains(Confirm & Proceed to Payment)",
                run: "click",
            },
            PaymentScreen.isShown(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            FeedbackScreen.isShown(),
            {
                content: "Epson LQ-350 receipt carries the mapped values",
                trigger: ".feedback-screen",
                async run() {
                    /* global posmodel */
                    const printer = posmodel.ticketPrinter;
                    printer._print = () => {}; // no blocking print dialog in headless tests
                    const order = posmodel.models["pos.order"].find(
                        (o) => o.partner_id?.name === "Nasser Al-Kuwari" && o.getGymLines().length
                    );
                    await printer.printOrderReceipt({ order });
                    const text = document.querySelector("#receipt-iframe-container iframe")
                        .contentDocument.body.innerText;
                    for (const expected of [
                        "Receipt No:",
                        "Nasser Al-Kuwari (GYM-",
                        "Coach Alex Rodriguez (07:00 PM)",
                        "6 Months Full Gym + PT 26",
                        "Cash",
                    ]) {
                        if (!text.includes(expected)) {
                            throw new Error(`LQ-350 receipt misses "${expected}":\n${text}`);
                        }
                    }
                    console.log("LQ-350 receipt:\n" + text);
                },
            },
        ].flat(),
});
