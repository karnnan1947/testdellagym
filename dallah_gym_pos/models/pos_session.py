from odoo import api, models
from odoo.fields import Domain


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config):
        data = super()._load_pos_data_models(config)
        data += ['res.branch']
        if 'hr.employee' not in data:
            data += ['hr.employee']
        return data


class ResBranch(models.Model):
    _name = 'res.branch'
    _inherit = ['res.branch', 'pos.load.mixin']

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'code', 'display_name']


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        return fields + ['is_gym_membership', 'membership_type', 'membership_duration_val',
                         'membership_duration_unit', 'pt_total_sessions']


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _load_pos_data_domain(self, data):
        domain = super()._load_pos_data_domain(data)
        # Coaches must be available for the PT slot section of the checkout modal
        return Domain.OR([Domain(domain), Domain('is_coach', '=', True)])

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        # Coaches loaded only for the checkout modal must never be selectable as cashiers
        cashier_ids = set(self.search(config._employee_domain(config.current_user_id.id)).ids) \
            if hasattr(config, '_employee_domain') else set()
        for employee in read_records:
            employee['_gym_coach_only'] = employee['id'] not in cashier_ids
        return read_records

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['is_coach', 'allowed_branch_ids']


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['member_id_code', 'is_gym_member', 'qid_number']
