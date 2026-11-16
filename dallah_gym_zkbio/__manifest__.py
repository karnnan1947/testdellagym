{
    'name': 'Dallah Gym - ZKBio CVSecurity REST API Connector',
    'version': '20.0.1.0.0',
    'category': 'Technical/Hardware Integration',
    'summary': 'Non-blocking REST connector to ZKBio CVSecurity 6.0.0_R (ZKTeco ProFace X [P] turnstiles) '
               'with retry queue and 10-minute check-in log sync.',
    'description': """
Non-Blocking REST API Biometric Connector linking Odoo 20 to Allied's ZKBio CVSecurity 6.0.0_R Server
for ZKTeco ProFace X [P] Face & Palm Turnstiles, featuring Retry Queue Protection and 10-Minute
Check-in Log Synchronization (DES00145).
    """,
    'author': 'AGM Global Services',
    'website': 'https://www.agmglobal.co/',
    'license': 'OPL-1',
    'depends': ['dallah_gym_core'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_zkbio.xml',
        'views/res_config_settings_views.xml',
        'views/res_branch_views.xml',
        'views/zkbio_sync_queue_views.xml',
    ],
    'installable': True,
    'application': False,
}
