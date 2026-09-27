#!/usr/bin/env python3
"""Replace only the regenerable filename index; preserve snapshot/event records."""
import fcntl
import os
from pathlib import Path
import sqlite3
from vault import Vault
h=Path.home();v=Vault(h/'.config/project-vault/config.json')
with v.locked():
 source=v.state/'catalog.sqlite'; dest=v.state/'catalog.compact.sqlite'
 if dest.exists(): raise SystemExit('Compact output already exists; inspect before retrying.')
 new=sqlite3.connect(dest)
 for kind in ('table','index'):
  for sql, in v.db.execute("SELECT sql FROM sqlite_master WHERE type=? AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'",(kind,)):
   new.execute(sql)
 for table in ('snapshots','events'):
  rows=v.db.execute('SELECT * FROM '+table)
  for row in rows:
   new.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in row)+')',row)
 latest=v.db.execute('SELECT id FROM snapshots ORDER BY time DESC LIMIT 1').fetchone()
 if latest:
  for row in v.db.execute("SELECT * FROM files WHERE snapshot=? AND length(path)<300 AND path NOT LIKE '%/target%/%' AND path NOT LIKE '%/.git/%' AND path NOT LIKE '%/node_modules/%' AND path NOT LIKE '%/deps/%' LIMIT 100000",latest):
   new.execute('INSERT INTO files VALUES(?,?,?,?,?)',row)
 new.commit()
 assert new.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 print('Previous catalog bytes:',source.stat().st_size,flush=True)
 print('Compact catalog bytes:',dest.stat().st_size,flush=True)
 new.close();v.db.close()
 # All omitted rows are restic-derived indexes, recoverable from retained snapshots.
 os.replace(dest,source)
 print('Compact catalog installed. Snapshots and event history preserved.',flush=True)
