from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        invoices = posted.filtered(lambda m: m.move_type == 'out_invoice')
        sale_lines = invoices.invoice_line_ids.sale_line_ids
        if sale_lines:
            memberships = self.env['gym.membership'].search(
                [('sale_line_id', 'in', sale_lines.ids), ('invoice_id', '=', False)])
            for membership in memberships:
                inv = membership.sale_line_id.invoice_lines.move_id.filtered(
                    lambda m: m in invoices)[:1]
                membership.invoice_id = inv
        return posted
