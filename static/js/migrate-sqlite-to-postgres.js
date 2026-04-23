require('dotenv').config();
const path = require('path');
const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const { Pool, types } = require('pg');

types.setTypeParser(20, value => Number(value));

const SQLITE_PATH = process.env.SQLITE_PATH || path.join(__dirname, '..', 'data', 'alhabeshi.sqlite');
const DATABASE_URL = process.env.DATABASE_URL;

const tables = [
  'products',
  'orders',
  'customers',
  'offers',
  'chat_messages',
  'members',
  'newsletter_subscribers',
  'admin_users',
  'sports_sources',
  'sports_articles',
  'store_settings'
];

async function main() {
  if (!DATABASE_URL) throw new Error('DATABASE_URL is required');

  const sqliteDb = await open({ filename: SQLITE_PATH, driver: sqlite3.Database });
  const pg = new Pool({ connectionString: DATABASE_URL, ssl: false });

  for (const table of tables) {
    const rows = await sqliteDb.all('SELECT * FROM ' + table);
    if (!rows.length) {
      console.log('skip empty table', table);
      continue;
    }

    const columns = Object.keys(rows[0]);
    const placeholders = columns.map((_, index) => '$' + (index + 1)).join(',');
    const sql = 'INSERT INTO ' + table + ' (' + columns.join(',') + ') VALUES (' + placeholders + ') ON CONFLICT DO NOTHING';

    for (const row of rows) {
      await pg.query(sql, columns.map(col => row[col]));
    }

    console.log('migrated', table, rows.length);
  }

  await sqliteDb.close();
  await pg.end();
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
