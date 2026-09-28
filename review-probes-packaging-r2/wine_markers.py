import sys, os, shutil
sys.dont_write_bytecode = True
src_text = open('/home/brunner56/kp-live-20260922/review-probes-packaging-r2/adversarial.py').read().split('ALL = [')[0]
src_text = src_text.replace("rm(P); P.mkdir(parents=True)", "P = P.parent / 'adv-wine'; rm(P); P.mkdir(parents=True)")
exec(src_text)
U = os.path.basename(os.environ['HOME'])
def mk(text):
    def m(src, out):
        (src / 'scripts/examples/cursed/w.lua').write_text('-- ' + text + '\n'); return {'look': ['w.lua'], 'bytes': [U.encode(), U.upper().encode(), U.capitalize().encode()]}
    return m
for label, text in [('c_users_lower', f'c:\\users\\{U}\\x'), ('drive_c_users', f'drive_c/users/{U}/x'),
                    ('C_USERS_upper', f'C:\\USERS\\{U}'), ('wine_z_home', f'Z:\\home\\{U}\\x'),
                    ('steamuser', 'drive_c/users/steamuser/AppData'), ('user_underscore', f'prefix_{U}_suffix'),
                    ('user_upper', U.upper()), ('user_capital', U.capitalize()),
                    ('media_user', f'/media/{U}/disk'), ('mnt_c_users', f'/mnt/c/Users/{U}')]:
    run(label, mk(text))
rm(P); print('cleanup done:', not P.exists())
