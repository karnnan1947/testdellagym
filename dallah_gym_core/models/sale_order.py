from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    branch_id = fields.Many2one('res.branch', string='Sales Branch', index=True)
    allowed_branch_ids = fields.Many2many(
        'res.branch', 'sale_order_gym_branch_rel', 'order_id', 'branch_id',
        string='Allowed Gate Branches',
        compute='_compute_allowed_branch_ids', store=True, readonly=False)
    has_gym_membership = fields.Boolean(compute='_compute_has_gym_membership')
    gym_membership_ids = fields.One2many('gym.membership', compute='_compute_gym_membership_ids',
                                         string='Memberships')

    @api.depends('branch_id')
    def _compute_allowed_branch_ids(self):
        for order in self:
            if order.branch_id:
                order.allowed_branch_ids = order.branch_id.default_allowed_branch_ids or order.branch_id

    @api.depends('order_line.product_id')
    def _compute_has_gym_membership(self):
        for order in self:
            order.has_gym_membership = any(order.order_line.product_id.mapped('is_gym_membership'))

    def _compute_gym_membership_ids(self):
        for order in self:
            order.gym_membership_ids = self.env['gym.membership'].search(
                [('sale_line_id', 'in', order.order_line.ids)])

    def _check_gym_coach_slots(self):
        """Raise if a PT line's coach slot conflicts with existing bookings."""
        Service = self.env['gym.membership.service']
        for order in self:
            for line in order.order_line.filtered(lambda l: l.product_id.is_gym_membership):
                tmpl = line.product_id.product_tmpl_id
                if tmpl.membership_type not in ('pt', 'class') or not tmpl.pt_total_sessions:
                    continue
                if not line.coach_id:
                    raise ValidationError(self.env._("Please select a coach for %s.", line.product_id.display_name))
                slots = Service.get_branch_coach_slots(
                    order.branch_id.id, line.coach_id.id, line.membership_start_date,
                    tmpl.pt_total_sessions, line.membership_end_date)
                slot = next((s for s in slots['morning'] + slots['evening'] if s['hour'] == line.pt_slot_hour), None)
                if not slot:
                    raise ValidationError(self.env._(
                        "%(coach)s does not work at the selected slot for %(product)s.",
                        coach=line.coach_id.name, product=line.product_id.display_name))
                if slot['booked']:
                    raise ValidationError(self.env._(
                        "%(coach)s is already booked at %(slot)s. Please choose another slot.",
                        coach=line.coach_id.name, slot=slot['label']))

    def action_check_coach_slots(self):
        self._check_gym_coach_slots()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._("All coach slots are available.")},
        }

    def _action_confirm(self):
        gym_orders = self.filtered('has_gym_membership')
        gym_orders._check_gym_coach_slots()
        res = super()._action_confirm()
        # sudo: salespeople / cashiers may not be gym managers or hold the branch
        Service = self.env['gym.membership.service'].sudo()
        for order in gym_orders:
            for line in order.order_line.filtered(lambda l: l.product_id.is_gym_membership):
                for _qty in range(max(int(line.product_uom_qty), 1)):
                    Service.finalize_membership_sale(
                        order.partner_id, line.product_id, line.membership_start_date,
                        allowed_branches=order.allowed_branch_ids, branch=order.branch_id,
                        coach=line.coach_id, slot_hour=line.pt_slot_hour,
                        amount_paid=line.price_total / max(line.product_uom_qty, 1),
                        sale_line=line)
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_gym_membership = fields.Boolean(related='product_id.is_gym_membership')
    membership_type = fields.Selection(related='product_id.membership_type')
    membership_start_date = fields.Date(string='Start Date', default=fields.Date.context_today)
    membership_end_date = fields.Date(
        string='End Date', compute='_compute_membership_end_date', store=True, readonly=False)
    coach_id = fields.Many2one('hr.employee', string='Assigned Coach', domain=[('is_coach', '=', True)])
    pt_slot_hour = fields.Float(string='Time Slot')

    @api.depends('product_id', 'membership_start_date')
    def _compute_membership_end_date(self):
        Service = self.env['gym.membership.service']
        for line in self:
            if line.product_id.is_gym_membership and line.membership_start_date:
                line.membership_end_date = Service.compute_end_date(line.product_id, line.membership_start_date)
            else:
                line.membership_end_date = False

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if self.product_id.is_gym_membership and self.membership_start_date and self.membership_end_date:
            vals['deferred_start_date'] = self.membership_start_date
            vals['deferred_end_date'] = self.membership_end_date
        return vals
