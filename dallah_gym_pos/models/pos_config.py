from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    gym_branch_id = fields.Many2one('res.branch', string='Counter Gym Branch')
    default_allowed_branch_ids = fields.Many2many(
        'res.branch', 'pos_config_gym_branch_rel', 'config_id', 'branch_id',
        string='Default Allowed Turnstiles')
    use_dot_matrix_receipt = fields.Boolean(string='Epson LQ-350 Continuous Receipt', default=True)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_gym_branch_id = fields.Many2one(related='pos_config_id.gym_branch_id', readonly=False)
    pos_default_allowed_branch_ids = fields.Many2many(
        related='pos_config_id.default_allowed_branch_ids', readonly=False)
    pos_use_dot_matrix_receipt = fields.Boolean(related='pos_config_id.use_dot_matrix_receipt', readonly=False)
