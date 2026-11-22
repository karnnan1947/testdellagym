from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    gym_branch_id = fields.Many2one('res.branch', string='Counter Gym Branch')
    default_allowed_branch_ids = fields.Many2many(
        'res.branch', 'pos_config_gym_branch_rel', 'config_id', 'branch_id',
        string='Default Allowed Turnstiles')
    use_dot_matrix_receipt = fields.Boolean(string='Epson LQ-350 Continuous Receipt', default=True)

    @api.constrains('gym_branch_id', 'picking_type_id')
    def _check_gym_branch_warehouse(self):
        for config in self:
            warehouse = config.gym_branch_id.warehouse_id
            if warehouse and config.picking_type_id.warehouse_id != warehouse:
                raise ValidationError(self.env._(
                    "POS '%(pos)s' belongs to branch %(branch)s, whose warehouse is %(wh)s, but its "
                    "operation type uses warehouse %(other)s. Stock would leave the wrong branch.",
                    pos=config.name, branch=config.gym_branch_id.name, wh=warehouse.name,
                    other=config.picking_type_id.warehouse_id.name or '-'))


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_gym_branch_id = fields.Many2one(related='pos_config_id.gym_branch_id', readonly=False)
    pos_default_allowed_branch_ids = fields.Many2many(
        related='pos_config_id.default_allowed_branch_ids', readonly=False)
    pos_use_dot_matrix_receipt = fields.Boolean(related='pos_config_id.use_dot_matrix_receipt', readonly=False)
