import sqlite3, os
DB_PATH = os.path.join(os.path.dirname(__file__), 'visitors.db')
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
print('VISITORS schema:')
for row in cur.execute('PRAGMA table_info(visitors)'):
    print(row)
print('VISITS schema:')
for row in cur.execute('PRAGMA table_info(visits)'):
    print(row)
conn.close()
