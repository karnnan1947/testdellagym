import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { debounce } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;

export class PtReceptionDashboard extends Component {
    static template = "dallah_gym_core.PtReceptionDashboard";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            data: null,
            branchId: false,
            date: DateTime.now().toISODate(),
            shift: DateTime.now().hour < 14 ? "morning" : "evening",
            search: "",
            booking: null, // {coach_id, coach_name, hour, label}
            memberQuery: "",
            memberResults: [],
        });
        this.onSearchInput = debounce(this.load.bind(this), 300);
        this.onMemberInput = debounce(this.searchMembers.bind(this), 300);
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("gym.pt.session", "get_reception_board_data", [
            this.state.branchId || false,
            this.state.date,
            this.state.search || false,
        ]);
        this.state.branchId = this.state.data.branch_id;
    }

    get rows() {
        return this.state.data?.grid?.[this.state.shift] || [];
    }

    get hours() {
        return this.state.data?.hours?.[this.state.shift] || [];
    }

    onBranchChange(ev) {
        this.state.branchId = parseInt(ev.target.value) || false;
        this.load();
    }

    onDateChange(ev) {
        this.state.date = ev.target.value;
        this.load();
    }

    shiftDay(days) {
        this.state.date = DateTime.fromISO(this.state.date).plus({ days }).toISODate();
        this.load();
    }

    setShift(shift) {
        this.state.shift = shift;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        this.onSearchInput();
    }

    cellClass(cell) {
        if (cell.highlight) {
            return "o_gym_cell_highlight";
        }
        if (cell.session_id) {
            return `o_gym_cell_booked o_gym_state_${cell.state}`;
        }
        if (cell.off_shift) {
            return "o_gym_cell_off";
        }
        return "o_gym_cell_free";
    }

    openSession(cell) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "gym.pt.session",
            res_id: cell.session_id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.load() });
    }

    startQuickBook(row, cell) {
        this.state.booking = {
            coach_id: row.coach_id,
            coach_name: row.coach_name,
            hour: cell.hour,
            label: cell.label,
        };
        this.state.memberQuery = "";
        this.state.memberResults = [];
    }

    cancelQuickBook() {
        this.state.booking = null;
    }

    onMemberQuery(ev) {
        this.state.memberQuery = ev.target.value;
        this.onMemberInput();
    }

    async searchMembers() {
        const q = this.state.memberQuery.trim();
        if (!q) {
            this.state.memberResults = [];
            return;
        }
        this.state.memberResults = await this.orm.call("res.partner", "name_search", [], {
            name: q,
            domain: [["is_gym_member", "=", true]],
            limit: 8,
        });
    }

    async confirmQuickBook(partner) {
        const b = this.state.booking;
        try {
            await this.orm.call("gym.pt.session", "quick_book", [
                partner[0],
                b.coach_id,
                this.state.branchId || false,
                this.state.date,
                b.hour,
            ]);
            this.notification.add(_t("Session booked for %s", partner[1]), { type: "success" });
            this.state.booking = null;
        } finally {
            await this.load();
        }
    }

    openCalendar() {
        this.action.doAction("dallah_gym_core.action_gym_pt_session");
    }
}

registry.category("actions").add("dallah_gym_pt_reception_board", PtReceptionDashboard);
