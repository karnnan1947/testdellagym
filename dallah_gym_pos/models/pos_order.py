import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    gym_branch_id = fields.Many2one('res.branch', string='Counter Gym Branch', index=True)
    allowed_branch_ids = fields.Many2many(
        'res.branch', 'pos_order_gym_branch_rel', 'order_id', 'branch_id',
        string='Permitted Gate Branches')
    gym_membership_finalized = fields.Boolean(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        # Every order (cafe included) carries its counter's branch: branch rules and branch P&L rely on it
        for vals in vals_list:
            if not vals.get('gym_branch_id'):
                session = self.env['pos.session'].browse(vals.get('session_id'))
                config = session.config_id if session else self.env['pos.config']
                vals['gym_branch_id'] = config.gym_branch_id.id or False
        return super().create(vals_list)

    @api.model
    def _check_gym_slots_from_ui(self, order):
        """Last-resort guard: reject the order when another terminal took the coach slot.

        The POS already re-checks the slots when the cashier clicks Validate (see
        PaymentValidationHook.js); this only covers the tiny window between that check and the sync.
        """
        data = order.get('lines') or []
        Service = self.env['gym.membership.service']
        branch_id = order.get('gym_branch_id')
        if isinstance(branch_id, (list, tuple)):
            branch_id = branch_id[0] if branch_id else False
        if not branch_id and order.get('session_id'):
            branch_id = self.env['pos.session'].browse(order['session_id']).config_id.gym_branch_id.id
        lines = []
        for command in data:
            vals = command[2] if isinstance(command, (list, tuple)) and len(command) > 2 else {}
            if (vals.get('qty') or 0) > 0:
                lines.append(vals)
        Service.check_slots(branch_id, lines)

    @api.model
    def _process_order(self, order, existing_order):
        if not existing_order:
            self._check_gym_slots_from_ui(order)
        order_id = super()._process_order(order, existing_order)
        pos_order = self.browse(order_id) if isinstance(order_id, int) else order_id
        if pos_order and pos_order.state in ('paid', 'done', 'invoiced'):
            try:
                with self.env.cr.savepoint():
                    pos_order._finalize_gym_memberships()
            except Exception:
                # Never block POS payment / receipt printing because of membership post-processing
                _logger.exception("Gym membership finalization failed for POS order %s", pos_order.name)
        return order_id

    def _finalize_gym_memberships(self):
        """Create memberships / PT sessions / gate sync once the order is paid."""
        # sudo: POS cashiers are branch-restricted; the paid sale must always produce its membership
        Service = self.env['gym.membership.service'].sudo()
        for order in self.filtered(lambda o: not o.gym_membership_finalized and o.partner_id):
            lines = order.lines.filtered(lambda l: l.product_id.is_gym_membership and l.qty > 0)
            if not lines:
                continue
            for line in lines:
                for _qty in range(max(int(line.qty), 1)):
                    Service.finalize_membership_sale(
                        order.partner_id, line.product_id,
                        line.membership_start_date or fields.Date.context_today(self),
                        allowed_branches=order.allowed_branch_ids,
                        branch=order.gym_branch_id or order.config_id.gym_branch_id,
                        coach=line.coach_id, slot_hour=line.pt_slot_hour,
                        amount_paid=line.price_subtotal_incl / max(line.qty, 1),
                        pos_line_id=line.id,
                        invoice=order.account_move if order.account_move else None)
            order.gym_membership_finalized = True

    def _prepare_account_move_line_data_from_base_line(self, base_lines):
        to_create = super()._prepare_account_move_line_data_from_base_line(base_lines)
        branch = self.gym_branch_id or self.config_id.gym_branch_id
        for item in to_create:
            line = item.get('metadata', {}).get('line')
            vals = item.get('account.move.line', {})
            if not line or vals.get('display_type') != 'product' or line._name != 'pos.order.line':
                continue
            if line.product_id.is_gym_membership and line.membership_start_date and line.membership_end_date:
                vals['deferred_start_date'] = line.membership_start_date
                vals['deferred_end_date'] = line.membership_end_date
            if branch.analytic_account_id and not vals.get('analytic_distribution'):
                vals['analytic_distribution'] = {str(branch.analytic_account_id.id): 100}
        return to_create


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    membership_start_date = fields.Date(string='Start Date')
    membership_end_date = fields.Date(string='End Date')
    coach_id = fields.Many2one('hr.employee', string='Assigned Coach')
    pt_slot_hour = fields.Float(string='Selected Slot Hour')

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ['membership_start_date', 'membership_end_date', 'coach_id', 'pt_slot_hour']
