import jwtmanager as j
h = j.hash_password('hunter2')
print('verify good:', j.verify_password('hunter2', h))
print('verify bad:', j.verify_password('wrong', h))
t = j.create_token('test@example.com')
print('decode:', j.verify_token(t))
print('bad token:', j.verify_token('garbage'))