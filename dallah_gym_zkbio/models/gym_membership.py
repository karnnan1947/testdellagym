from odoo import models


class GymMembership(models.Model):
    _inherit = 'gym.membership'

    def _gym_gate_push(self):
        res = super()._gym_gate_push()
        Service = self.env['zkbio.api.service']
        for partner in self.partner_id:
            Service.push_member_access(partner)
        return res

    def _gym_gate_suspend(self):
        res = super()._gym_gate_suspend()
        Service = self.env['zkbio.api.service']
        for partner in self.partner_id:
            # another active plan keeps the member's gate open: only a lone plan suspends access
            if partner._gym_repoint_current_membership(exclude=self & partner.gym_membership_ids):
                Service.push_member_access(partner)
            else:
                Service.suspend_member_gates(partner)
        return res

    def _gym_gate_revoke(self):
        res = super()._gym_gate_revoke()
        Service = self.env['zkbio.api.service']
        for partner in self.partner_id:
            if partner._gym_repoint_current_membership(exclude=self & partner.gym_membership_ids):
                Service.push_member_access(partner)
            else:
                Service.revoke_member_gates(partner)
        return res

    def _cron_process_zkbio_sync(self):
        return self.env['zkbio.api.service']._cron_process_zkbio_sync()
